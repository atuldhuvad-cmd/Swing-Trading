"""PDF worker memory containment and distinct parser errors.

Windows Job Object behaviour is tested here with mocked Windows APIs and handles;
real Job Object execution needs verification on Windows. All PDFs are synthetic.
"""
import ctypes
import importlib.util
import os
import sys
import threading

import pytest

from app.services import broker_pdf_extraction as extraction
from app.services import broker_upload_service as uploads
from app.services import windows_job
from tests.pdf_factory import make_pdf, make_slow_pdf

WORKER = extraction._WORKER_PATH


# ---------------------------------------------------------------- WorkerJob with a fake kernel32

class FakeKernel32:
    def __init__(self, create_ok=True, set_ok=True, assign_ok=True):
        self.calls, self.create_ok, self.set_ok, self.assign_ok = [], create_ok, set_ok, assign_ok
        self.info = None

    def CreateJobObjectW(self, attrs, name):
        self.calls.append("create")
        return 0xABC if self.create_ok else None

    def SetInformationJobObject(self, handle, cls, info_ref, size):
        self.calls.append(("set", handle, cls, size))
        info = ctypes.cast(info_ref, ctypes.POINTER(windows_job.JOBOBJECT_EXTENDED_LIMIT_INFORMATION)).contents
        self.info = (info.BasicLimitInformation.LimitFlags, info.ProcessMemoryLimit)
        return self.set_ok

    def AssignProcessToJobObject(self, handle, process):
        self.calls.append(("assign", handle, process))
        return self.assign_ok

    def TerminateJobObject(self, handle, code):
        self.calls.append(("terminate", handle, code))
        return True

    def QueryInformationJobObject(self, handle, cls, info_ref, size, ret):
        info = ctypes.cast(info_ref, ctypes.POINTER(windows_job.JOBOBJECT_EXTENDED_LIMIT_INFORMATION)).contents
        info.PeakProcessMemoryUsed = 123
        return True

    def CloseHandle(self, handle):
        self.calls.append(("close", handle))
        return True


def test_job_is_created_with_memory_limit_and_kill_on_close():
    k = FakeKernel32()
    job = windows_job.WorkerJob(512 * 1024 * 1024, kernel32=k)
    flags, limit = k.info
    assert flags & windows_job.JOB_OBJECT_LIMIT_PROCESS_MEMORY
    assert flags & windows_job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    assert limit == 512 * 1024 * 1024
    assert k.calls[1] == ("set", 0xABC, 9, ctypes.sizeof(windows_job.JOBOBJECT_EXTENDED_LIMIT_INFORMATION))
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        assert ctypes.sizeof(windows_job.JOBOBJECT_EXTENDED_LIMIT_INFORMATION) == 144  # Windows x64 layout
    job.assign(777)
    job.terminate()
    assert job.peak_process_memory() == 123
    job.close()
    job.close()  # idempotent
    assert ("assign", 0xABC, 777) in k.calls and ("terminate", 0xABC, 1) in k.calls
    assert k.calls.count(("close", 0xABC)) == 1


def test_job_creation_failures_close_the_handle_and_raise():
    with pytest.raises(OSError):
        windows_job.WorkerJob(1, kernel32=FakeKernel32(create_ok=False))
    k = FakeKernel32(set_ok=False)
    with pytest.raises(OSError):
        windows_job.WorkerJob(1, kernel32=k)
    assert ("close", 0xABC) in k.calls
    job = windows_job.WorkerJob(1, kernel32=FakeKernel32(assign_ok=False))
    with pytest.raises(OSError):
        job.assign(1)


# ---------------------------------------------------------------- Windows code path with a mocked job

class RecordingJob:
    def __init__(self, peak=None, assign_error=False):
        self.events, self.peak, self.assign_error = [], peak, assign_error

    def assign(self, handle):
        self.events.append(("assign", handle))
        if self.assign_error:
            raise OSError("assign failed")

    def terminate(self):
        self.events.append("terminate")

    def peak_process_memory(self):
        return self.peak

    def close(self):
        self.events.append("close")


@pytest.fixture
def windows_path(monkeypatch):
    """Run the Windows branch on this platform with a recording job; the pid stands in for the handle."""
    jobs, procs = [], []
    real_popen = extraction.subprocess.Popen

    def popen(*a, **k):
        p = real_popen(*a, **k)
        procs.append(p)
        return p

    def factory(**kw):
        def create():
            job = RecordingJob(**kw)
            jobs.append(job)
            return job
        monkeypatch.setattr(extraction, "_create_worker_job", create)

    monkeypatch.setattr(extraction, "_IS_WINDOWS", True)
    monkeypatch.setattr(extraction, "_process_handle", lambda p: p.pid)
    monkeypatch.setattr(extraction.subprocess, "Popen", popen)
    factory()
    return jobs, procs, factory


def test_windows_success_assigns_worker_and_closes_job(windows_path):
    jobs, procs, _ = windows_path
    ex = extraction.extract_fields_isolated(make_pdf([["synthetic text"]]))
    assert ex.page_count == 1
    assert jobs[0].events == [("assign", procs[0].pid), "close"]
    assert procs[0].returncode == 0


def test_windows_timeout_terminates_job_tree_and_closes_it(windows_path, monkeypatch):
    jobs, procs, _ = windows_path
    monkeypatch.setattr(extraction, "PARSE_TIMEOUT_SECONDS", 1.0)
    with pytest.raises(extraction.PdfExtractionError) as exc:
        extraction.extract_fields_isolated(make_slow_pdf())
    assert exc.value.category == extraction.TIMEOUT
    assert jobs[0].events[0] == ("assign", procs[0].pid)
    assert "terminate" in jobs[0].events and jobs[0].events[-1] == "close"
    assert procs[0].returncode is not None


def test_windows_failure_path_closes_job(windows_path):
    jobs, _, _ = windows_path
    with pytest.raises(extraction.PdfExtractionError) as exc:
        extraction.extract_fields_isolated(b"%PDF-1.4\n" + b"0" * 2000)
    assert exc.value.category == extraction.UNREADABLE_PDF
    assert jobs[0].events[-1] == "close"


def test_windows_refuses_to_parse_without_containment(windows_path):
    jobs, procs, factory = windows_path
    factory(assign_error=True)
    with pytest.raises(extraction.PdfExtractionError) as exc:
        extraction.extract_fields_isolated(make_pdf([["x"]]))
    assert exc.value.category == extraction.PARSER_FAILED
    assert procs[0].returncode is not None and jobs[0].events[-1] == "close"


def test_windows_worker_killed_at_memory_limit_is_a_resource_error(windows_path, monkeypatch, tmp_path):
    jobs, _, factory = windows_path
    factory(peak=extraction.WORKER_MEMORY_LIMIT_BYTES)
    dying = tmp_path / "dying_worker.py"
    dying.write_text("import sys; sys.stdin.buffer.read(); sys.exit(3)\n")
    monkeypatch.setattr(extraction, "_WORKER_PATH", dying)
    with pytest.raises(extraction.PdfExtractionError) as exc:
        extraction.extract_fields_isolated(make_pdf([["x"]]))
    assert exc.value.category == extraction.RESOURCE_LIMIT
    assert str(exc.value) == extraction.RESOURCE_LIMIT_MESSAGE


# ---------------------------------------------------------------- MemoryError and the real POSIX limit

def _load_worker():
    spec = importlib.util.spec_from_file_location("pdf_text_worker_under_test", WORKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_memory_error_on_a_page_is_a_resource_limit_not_an_empty_page(monkeypatch):
    import pypdf

    class Page:
        def extract_text(self):
            raise MemoryError

    class Reader:
        is_encrypted = False

        def __init__(self, *a, **k):
            self.pages = [Page(), Page()]

    monkeypatch.setattr(pypdf, "PdfReader", Reader)
    assert _load_worker().read(b"%PDF-", 60, 1000) == {"ok": False, "error": "RESOURCE_LIMIT"}


def test_other_page_errors_still_become_empty_pages(monkeypatch):
    import pypdf

    class Page:
        def extract_text(self):
            raise ValueError("broken page")

    class Reader:
        is_encrypted = False

        def __init__(self, *a, **k):
            self.pages = [Page()]

    monkeypatch.setattr(pypdf, "PdfReader", Reader)
    assert _load_worker().read(b"%PDF-", 60, 1000)["pages"] == [""]


@pytest.mark.skipif(os.name == "nt", reason="POSIX address-space limit; Windows uses the Job Object (verify on Windows)")
def test_memory_bomb_hits_the_memory_limit_before_the_timeout(monkeypatch):
    monkeypatch.setattr(extraction, "WORKER_MEMORY_LIMIT_BYTES", 256 * 1024 * 1024)
    monkeypatch.setattr(extraction, "PARSE_TIMEOUT_SECONDS", 25.0)
    with pytest.raises(extraction.PdfExtractionError) as exc:
        extraction.extract_fields_isolated(make_slow_pdf(ops_per_page=5_000_000))
    assert exc.value.category == extraction.RESOURCE_LIMIT


def test_worker_uses_the_base_interpreter_not_a_venv_launcher(monkeypatch, tmp_path):
    import pypdf

    base = tmp_path / "python-base"
    base.write_text("")
    monkeypatch.setattr(extraction.sys, "_base_executable", str(base), raising=False)
    cmd = extraction._worker_command()
    assert cmd[:4] == [str(base), "-I", "-S", str(WORKER)]
    assert cmd[-1] == str(os.path.dirname(os.path.dirname(os.path.realpath(pypdf.__file__))))
    monkeypatch.setattr(extraction.sys, "_base_executable", str(tmp_path / "absent"), raising=False)
    assert extraction._worker_command()[0] == sys.executable  # falls back when the base is unavailable


def test_default_memory_limit_is_512_mib_and_normal_pdfs_parse_under_it():
    assert extraction.WORKER_MEMORY_LIMIT_BYTES == 512 * 1024 * 1024
    assert extraction.extract_fields_isolated(make_pdf([["synthetic"]] * 60)).page_count == 60


# ---------------------------------------------------------------- distinct parser failures

@pytest.mark.parametrize("script", [
    'import sys; sys.stdin.buffer.read(); print("not json")',                                # protocol
    'import sys, json; sys.stdin.buffer.read(); print(json.dumps({"ok": False, "error": "WORKER"}))',  # import failure
    'import sys, json; sys.stdin.buffer.read(); print(json.dumps({"ok": True, "pages": "x"}))',        # bad shape
    'raise SystemExit(1)',                                                                     # crash
])
def test_worker_failures_are_parser_failed_not_too_complex(monkeypatch, tmp_path, script):
    worker = tmp_path / "worker.py"
    worker.write_text(script + "\n")
    monkeypatch.setattr(extraction, "_WORKER_PATH", worker)
    with pytest.raises(extraction.PdfExtractionError) as exc:
        extraction.extract_fields_isolated(make_pdf([["x"]]))
    assert exc.value.category == extraction.PARSER_FAILED
    assert str(exc.value) == extraction.PARSER_FAILED_MESSAGE and "TOO_COMPLEX" not in str(exc.value)


def test_worker_that_cannot_start_is_parser_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(extraction, "_worker_command", lambda: [str(tmp_path / "missing-python"), str(WORKER)])
    with pytest.raises(extraction.PdfExtractionError) as exc:
        extraction.extract_fields_isolated(make_pdf([["x"]]))
    assert exc.value.category == extraction.PARSER_FAILED


def test_error_categories_have_distinct_messages():
    messages = {extraction.PdfExtractionError.of(c).args[0] for c in (
        extraction.TIMEOUT, extraction.RESOURCE_LIMIT, extraction.BUSY, extraction.UNREADABLE_PDF, extraction.PARSER_FAILED)}
    assert len(messages) == 5


@pytest.fixture
def no_uploads(monkeypatch, tmp_path):
    monkeypatch.setattr(uploads, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(uploads, "MANIFEST_PATH", tmp_path / "uploads" / "manifest.json")
    monkeypatch.setattr(uploads, "BASE_DIR", tmp_path)


def test_api_status_codes_per_category(client, no_uploads, monkeypatch, tmp_path):
    pdf = {"file": ("r.pdf", make_pdf([["x"]]), "application/pdf")}
    broken = tmp_path / "broken.py"
    broken.write_text("raise SystemExit(1)\n")
    monkeypatch.setattr(extraction, "_WORKER_PATH", broken)
    resp = client.post("/api/broker-uploads/preview", files=pdf)
    assert resp.status_code == 500 and resp.json()["detail"] == extraction.PARSER_FAILED_MESSAGE
    assert str(tmp_path) not in resp.text and "Traceback" not in resp.text

    monkeypatch.setattr(extraction, "_WORKER_PATH", WORKER)
    monkeypatch.setattr(extraction, "_PARSE_SLOTS", threading.BoundedSemaphore(1))
    monkeypatch.setattr(extraction, "PARSE_TIMEOUT_SECONDS", 0.2)
    extraction._PARSE_SLOTS.acquire()  # every parse slot is busy
    try:
        resp = client.post("/api/broker-uploads/preview", files=pdf)
    finally:
        extraction._PARSE_SLOTS.release()
    assert resp.status_code == 503 and resp.json()["detail"] == extraction.BUSY_MESSAGE
