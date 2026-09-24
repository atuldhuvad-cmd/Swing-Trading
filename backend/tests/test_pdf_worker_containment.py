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


def _never(*_a, **_k):
    raise AssertionError("must not be reached")


def _assert_slots_free():
    """Every parser slot was released."""
    taken = [extraction._PARSE_SLOTS.acquire(blocking=False) for _ in range(extraction.MAX_CONCURRENT_PARSES)]
    for ok in taken:
        if ok:
            extraction._PARSE_SLOTS.release()
    assert all(taken)


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
        self.info = (info.BasicLimitInformation.LimitFlags, info.ProcessMemoryLimit,
                     info.BasicLimitInformation.ActiveProcessLimit)
        if self.set_ok == "raise":
            raise TypeError("simulated ctypes failure")
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
    flags, limit, active = k.info
    assert flags == (0x00000008 | 0x00000100 | 0x00002000 | 0x00000400)  # active-process, memory, kill-on-close, die-on-exception
    assert active == 1 and limit == 512 * 1024 * 1024
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
    monkeypatch.setattr(extraction, "_base_interpreter", lambda: sys.executable)  # a resolved base interpreter
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
    for windows in (False, True):
        monkeypatch.setattr(extraction, "_IS_WINDOWS", windows)
        cmd = extraction._worker_command()
        assert cmd[:4] == [str(base), "-I", "-S", str(WORKER)]
        assert cmd[-1] == str(os.path.dirname(os.path.dirname(os.path.realpath(pypdf.__file__))))


@pytest.mark.parametrize("base", ["unset", "", "missing", "launcher"])
def test_windows_without_a_trustworthy_base_interpreter_fails_closed(monkeypatch, tmp_path, base):
    monkeypatch.setattr(extraction, "_IS_WINDOWS", True)
    if base == "unset":
        monkeypatch.delattr(extraction.sys, "_base_executable", raising=False)
    elif base == "missing":
        monkeypatch.setattr(extraction.sys, "_base_executable", str(tmp_path / "absent" / "python.exe"), raising=False)
    elif base == "launcher":  # only the venv launcher is known
        launcher = tmp_path / "Scripts" / "python.exe"
        launcher.parent.mkdir()
        launcher.write_text("")
        monkeypatch.setattr(extraction.sys, "_base_executable", str(launcher), raising=False)
        monkeypatch.setattr(extraction.sys, "executable", str(launcher))
        monkeypatch.setattr(extraction.sys, "prefix", str(tmp_path))
        monkeypatch.setattr(extraction.sys, "base_prefix", str(tmp_path / "base"))
    else:
        monkeypatch.setattr(extraction.sys, "_base_executable", base, raising=False)
    started = []
    monkeypatch.setattr(extraction.subprocess, "Popen", lambda *a, **k: started.append(a) or _never())
    with pytest.raises(extraction.PdfExtractionError) as exc:
        extraction.extract_fields_isolated(make_pdf([["x"]]))
    assert exc.value.category == extraction.PARSER_FAILED and str(exc.value) == extraction.PARSER_FAILED_MESSAGE
    assert started == []  # no worker, so no PDF bytes anywhere
    _assert_slots_free()


def test_posix_may_use_the_venv_interpreter_when_no_base_is_known(monkeypatch):
    monkeypatch.setattr(extraction, "_IS_WINDOWS", False)
    monkeypatch.delattr(extraction.sys, "_base_executable", raising=False)
    assert extraction._worker_command()[0] == sys.executable


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


# ---------------------------------------------------------------- job setup failures at every stage

class RecordingPopen(extraction.subprocess.Popen):
    instances = []

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.inputs = []
        RecordingPopen.instances.append(self)

    def communicate(self, input=None, timeout=None):
        self.inputs.append(input)
        return super().communicate(input=input, timeout=timeout)


class RaisingKernel32(FakeKernel32):
    def __init__(self, assign_exc=None, **kw):
        super().__init__(**kw)
        self.assign_exc = assign_exc

    def AssignProcessToJobObject(self, handle, process):
        self.calls.append(("assign", handle, process))
        if self.assign_exc:
            raise self.assign_exc
        return self.assign_ok


@pytest.fixture
def setup_stage(monkeypatch):
    RecordingPopen.instances = []
    monkeypatch.setattr(extraction, "_IS_WINDOWS", True)
    monkeypatch.setattr(extraction, "_base_interpreter", lambda: sys.executable)
    monkeypatch.setattr(extraction.subprocess, "Popen", RecordingPopen)

    def use(kernel32, handle=lambda p: p.pid):
        monkeypatch.setattr(extraction, "_create_worker_job",
                            lambda: windows_job.WorkerJob(extraction.WORKER_MEMORY_LIMIT_BYTES, kernel32=kernel32))
        monkeypatch.setattr(extraction, "_process_handle", handle)
    return use


@pytest.mark.parametrize("stage", ["create", "set_info_false", "set_info_raises", "assign_false",
                                   "assign_raises", "process_handle_raises", "factory_raises"])
def test_every_job_setup_failure_is_parser_failed_and_cleaned_up(setup_stage, monkeypatch, stage):
    k = {"create": FakeKernel32(create_ok=False), "set_info_false": FakeKernel32(set_ok=False),
         "set_info_raises": FakeKernel32(set_ok="raise"), "assign_false": FakeKernel32(assign_ok=False),
         "assign_raises": RaisingKernel32(assign_exc=RuntimeError("simulated")),
         "process_handle_raises": FakeKernel32(), "factory_raises": FakeKernel32()}[stage]
    handle = (lambda p: (_ for _ in ()).throw(AttributeError("no _handle"))) if stage == "process_handle_raises" else (lambda p: p.pid)
    setup_stage(k, handle)
    if stage == "factory_raises":
        monkeypatch.setattr(extraction, "_create_worker_job", lambda: (_ for _ in ()).throw(ValueError("ctypes missing")))
    pdf = make_pdf([["synthetic"]])
    with pytest.raises(extraction.PdfExtractionError) as exc:
        extraction.extract_fields_isolated(pdf)
    assert exc.value.category == extraction.PARSER_FAILED and str(exc.value) == extraction.PARSER_FAILED_MESSAGE
    assert "simulated" not in str(exc.value) and "_handle" not in str(exc.value)
    proc = RecordingPopen.instances[0]
    assert proc.returncode is not None                       # the started worker was terminated and reaped
    assert all(i is None for i in proc.inputs)               # PDF bytes were never sent
    created = stage not in ("create", "factory_raises")
    assert k.calls.count(("close", 0xABC)) == (1 if created else 0)  # partial handle closed exactly once
    _assert_slots_free()


def test_keyboard_interrupt_during_setup_propagates_with_cleanup(setup_stage):
    k = RaisingKernel32(assign_exc=KeyboardInterrupt())
    setup_stage(k)
    with pytest.raises(KeyboardInterrupt):
        extraction.extract_fields_isolated(make_pdf([["x"]]))
    proc = RecordingPopen.instances[0]
    assert proc.returncode is not None and all(i is None for i in proc.inputs)
    assert k.calls.count(("close", 0xABC)) == 1
    _assert_slots_free()


def test_successful_setup_sends_pdf_only_after_assignment(setup_stage):
    k = FakeKernel32()
    setup_stage(k)
    order = []
    k_assign = k.AssignProcessToJobObject
    k.AssignProcessToJobObject = lambda h, p: order.append("assign") or k_assign(h, p)
    real_comm = RecordingPopen.communicate

    def comm(self, input=None, timeout=None):
        if input is not None:
            order.append("pdf")
        return real_comm(self, input=input, timeout=timeout)

    RecordingPopen.communicate = comm
    try:
        assert extraction.extract_fields_isolated(make_pdf([["x"]])).page_count == 1
    finally:
        RecordingPopen.communicate = real_comm
    assert order == ["assign", "pdf"] and k.calls[-1] == ("close", 0xABC)


# ---------------------------------------------------------------- worker import order (-I -S, appended venv folder)

def _run_worker(site_dir, content=b"%PDF-1.4\n", python=None):
    import json as _json
    import subprocess as sp
    python = python or extraction._worker_command()[0]
    out = sp.run([python, "-I", "-S", str(WORKER), "60", "100000", str(1024 ** 3), str(site_dir)],
                 input=content, capture_output=True, timeout=60).stdout
    return _json.loads(out)


def test_pypdf_loads_from_the_supplied_venv_folder_and_no_site_packages():
    import subprocess as sp
    import pypdf

    cmd = extraction._worker_command()
    site_dir = cmd[-1]
    probe = ("import sys; sys.path.append(sys.argv[1]); import pypdf; "
             "print(pypdf.__file__); print(sys.flags.no_site, sys.flags.isolated); "
             "print([p for p in sys.path[:-1] if 'site-packages' in p or 'dist-packages' in p])")
    out = sp.run([cmd[0], "-I", "-S", "-c", probe, site_dir], capture_output=True, text=True, timeout=60).stdout.splitlines()
    assert os.path.realpath(out[0]) == os.path.realpath(pypdf.__file__)
    assert out[1] == "1 1" and out[2] == "[]"   # no system or user site-packages at all
    assert _run_worker(site_dir, make_pdf([["synthetic"]]))["ok"] is True


def test_supplied_folder_cannot_shadow_the_standard_library(tmp_path):
    site = tmp_path / "site"
    (site / "pypdf").mkdir(parents=True)
    (site / "hashlib.py").write_text("raise ImportError('shadowed stdlib module was imported')\n")
    (site / "pypdf" / "__init__.py").write_text(
        "import hashlib, os\n"
        "assert 'site' not in os.path.dirname(hashlib.__file__).split(os.sep)[-1:]\n"
        "class PdfReader:\n    def __init__(self, *a, **k):\n        raise ValueError('synthetic reader')\n")
    # The fake pypdf imports; hashlib comes from the standard library, so reading reports UNREADABLE, not WORKER.
    assert _run_worker(site) == {"ok": False, "error": "UNREADABLE"}


def test_worker_without_pypdf_in_the_supplied_folder_is_parser_failed(monkeypatch, tmp_path):
    empty = tmp_path / "empty-site"
    empty.mkdir()
    assert _run_worker(empty) == {"ok": False, "error": "WORKER"}
    real = extraction._worker_command
    monkeypatch.setattr(extraction, "_worker_command", lambda: real()[:-1] + [str(empty)])
    with pytest.raises(extraction.PdfExtractionError) as exc:
        extraction.extract_fields_isolated(make_pdf([["x"]]))
    assert exc.value.category == extraction.PARSER_FAILED
