"""Read-only field extraction from broker research PDFs.

Extraction is a convenience for the intake preview. The visible PDF stays
authoritative: every value comes back with a status, and anything that is not
found, or found with more than one distinct value, is UNKNOWN (never guessed).
Nothing here touches the database or the file system.

Supported layouts are the broker-authored reports this project receives
(typically discovered on Trendlyne): Motilal Oswal, ICICI Securities and Axis
Securities. An unrecognised layout yields UNKNOWN fields, not an error.

Report text is treated as data only.
"""
from __future__ import annotations

import io
import json
import os
import re
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError

KNOWN = "KNOWN"
UNKNOWN = "UNKNOWN"
AMBIGUOUS = "AMBIGUOUS"      # more than one distinct value found
NOT_STATED = "NOT_STATED"    # optional field the report does not state

MAX_PAGES = 60
MAX_TEXT_CHARS = 1_000_000        # extracted text across all read pages
PARSE_TIMEOUT_SECONDS = 30.0      # the isolated parser is killed after this
MAX_CONCURRENT_PARSES = 2         # at most this many parser processes at once
WORKER_MEMORY_LIMIT_BYTES = 512 * 1024 * 1024  # per parser process (Windows Job Object / POSIX RLIMIT_AS)
_IS_WINDOWS = os.name == "nt"
_WORKER_PATH = Path(__file__).with_name("pdf_text_worker.py")
_PARSE_SLOTS = threading.BoundedSemaphore(MAX_CONCURRENT_PARSES)

# Each broker needs at least two independent signatures before it is identified.
BROKER_SIGNATURES: dict[str, list[str]] = {
    "Motilal Oswal": [
        r"Motilal Oswal Financial Services",
        r"Motilal Oswal research is available",
        r"@motilaloswal\.com",
    ],
    "ICICI Securities": [
        r"ICICI Securities Limited is the author",
        r"@icicisecurities\.com",
        r"ICICI Securities Limited SEBI Registration",
    ],
    "Axis Securities": [
        r"Axis Securities Limited",
        r"@axissecurities\.in",
        r"AXIS SECURITIES",
    ],
}

_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], start=1)}
_MONTHS.update({k[:3]: v for k, v in list(_MONTHS.items())})
_MONTHS["sept"] = 9

_DATE_RX = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|"
    r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec),?\s+(20\d\d)\b",
    re.IGNORECASE,
)
_NUM = r"([\d,]+(?:\.\d+)?)"
_CORE_RATINGS = ("STRONG BUY", "BUY", "ACCUMULATE", "ADD", "HOLD", "NEUTRAL", "REDUCE", "SELL")


# Error categories for the isolated parser (fixed, client-safe messages).
TIMEOUT, RESOURCE_LIMIT, BUSY, UNREADABLE_PDF, PARSER_FAILED = (
    "TIMEOUT", "RESOURCE_LIMIT", "BUSY", "UNREADABLE", "PARSER_FAILED")

UNREADABLE_MESSAGE = "File could not be read as a PDF"
TIMEOUT_MESSAGE = "PDF_PARSE_TIMEOUT: the PDF took too long to read and was rejected"
RESOURCE_LIMIT_MESSAGE = "PDF_TOO_COMPLEX: the PDF exceeds the memory or text limit and was rejected"
BUSY_MESSAGE = "PDF_PARSER_BUSY: other PDFs are being read; try again shortly"
PARSER_FAILED_MESSAGE = "PDF_PARSER_FAILED: the PDF reader could not run; nothing was read"

_MESSAGES = {TIMEOUT: TIMEOUT_MESSAGE, RESOURCE_LIMIT: RESOURCE_LIMIT_MESSAGE, BUSY: BUSY_MESSAGE,
             UNREADABLE_PDF: UNREADABLE_MESSAGE, PARSER_FAILED: PARSER_FAILED_MESSAGE}


class PdfExtractionError(Exception):
    """The file cannot be read as a PDF, exceeds a limit, or the reader failed.

    ``category`` is one of TIMEOUT, RESOURCE_LIMIT, BUSY, UNREADABLE, PARSER_FAILED.
    Messages are fixed, client-safe text: no stack trace, no local path.
    """

    def __init__(self, message: str, category: str = UNREADABLE_PDF):
        super().__init__(message)
        self.category = category

    @classmethod
    def of(cls, category: str) -> "PdfExtractionError":
        return cls(_MESSAGES[category], category)


@dataclass
class Field:
    value: Any = None
    status: str = UNKNOWN
    note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        v = self.value
        if isinstance(v, Decimal):
            v = format(v, "f")
        elif isinstance(v, (date, datetime)):
            v = v.isoformat()
        return {"value": v, "status": self.status, "note": self.note}


@dataclass
class Extraction:
    page_count: int = 0
    text_chars: int = 0
    broker: Field = field(default_factory=Field)
    company_name: Field = field(default_factory=Field)
    bloomberg_code: Field = field(default_factory=Field)
    report_type: Field = field(default_factory=Field)
    report_date: Field = field(default_factory=Field)
    original_rating: Field = field(default_factory=Field)
    rating_core: Field = field(default_factory=Field)
    report_cmp: Field = field(default_factory=Field)
    cmp_as_of: Field = field(default_factory=lambda: Field(status=NOT_STATED))
    target: Field = field(default_factory=Field)
    previous_target: Field = field(default_factory=lambda: Field(status=NOT_STATED))
    entry_low: Field = field(default_factory=lambda: Field(status=NOT_STATED))
    entry_high: Field = field(default_factory=lambda: Field(status=NOT_STATED))
    stop_loss: Field = field(default_factory=lambda: Field(status=NOT_STATED))
    time_horizon: Field = field(default_factory=lambda: Field(status=NOT_STATED))
    analysts: Field = field(default_factory=Field)
    warnings: list[str] = field(default_factory=list)

    def fields(self) -> dict[str, Field]:
        return {k: v for k, v in self.__dict__.items() if isinstance(v, Field)}

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {k: f.as_dict() for k, f in self.fields().items()}
        out.update({"page_count": self.page_count, "text_chars": self.text_chars, "warnings": list(self.warnings)})
        return out


# ---------------------------------------------------------------- helpers

def parse_decimal(raw: str | None) -> Decimal | None:
    """Decimal from '3,105' / '6,020.50'; None if not a clean positive number."""
    if raw is None:
        return None
    s = raw.strip().replace(",", "")
    if not re.fullmatch(r"\d+(?:\.\d+)?", s):
        return None
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return d if d > 0 else None


def parse_date(text: str) -> date | None:
    m = _DATE_RX.search(text)
    if not m:
        return None
    day, mon, year = int(m.group(1)), _MONTHS.get(m.group(2).lower()), int(m.group(3))
    try:
        return date(year, mon, day)
    except (TypeError, ValueError):
        return None


def _single(values: list[Any], name: str, warnings: list[str]) -> Field:
    distinct = list(dict.fromkeys(values))
    if not distinct:
        return Field(None, UNKNOWN, f"{name} not found")
    if len(distinct) > 1:
        warnings.append(f"AMBIGUOUS_{name.upper().replace(' ', '_')}: {', '.join(str(v) for v in distinct)}")
        return Field(None, AMBIGUOUS, f"{len(distinct)} different values found")
    return Field(distinct[0], KNOWN)


def _lines(text: str) -> list[str]:
    return [" ".join(line.split()) for line in text.splitlines() if line.strip()]


def read_pdf_pages(content: bytes) -> tuple[list[str], bool]:
    """Return (page texts, encrypted). Raises PdfExtractionError for unreadable files."""
    try:
        reader = PdfReader(io.BytesIO(content), strict=False)
        encrypted = bool(reader.is_encrypted)
        if encrypted:
            try:
                encrypted = reader.decrypt("") == 0
            except Exception:  # noqa: BLE001 - any failure means we cannot read it
                encrypted = True
        if encrypted:
            return [], True
        pages = []
        for i, page in enumerate(reader.pages):
            if i >= MAX_PAGES:
                break
            try:
                pages.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001 - a broken page must not abort the preview
                pages.append("")
        return pages, False
    except PdfReadError as exc:
        raise PdfExtractionError(f"File could not be read as a PDF: {exc.__class__.__name__}") from exc
    except Exception as exc:  # noqa: BLE001 - malformed PDFs raise many exception types; never a 500
        raise PdfExtractionError(f"File could not be read as a PDF: {exc.__class__.__name__}") from exc


# ---------------------------------------------------------------- field rules

def _broker(full: str, warnings: list[str]) -> Field:
    scores = {}
    for broker, sigs in BROKER_SIGNATURES.items():
        hits = sum(1 for s in sigs if re.search(s, full, re.IGNORECASE))
        if hits:
            scores[broker] = hits
    strong = [b for b, n in scores.items() if n >= 2]
    if len(strong) == 1:
        return Field(strong[0], KNOWN, f"{scores[strong[0]]} broker signatures")
    if len(strong) > 1:
        warnings.append(f"AMBIGUOUS_BROKER: {', '.join(sorted(strong))}")
        return Field(None, AMBIGUOUS, "more than one broker identified")
    if scores:
        warnings.append(f"WEAK_BROKER_SIGNATURE: {', '.join(sorted(scores))}")
    return Field(None, UNKNOWN, "broker not identified")


def _report_date(p1: str, p2: str, warnings: list[str]) -> Field:
    cands = []
    for m in _DATE_RX.finditer(p1):
        before = p1[max(0, m.start() - 12):m.start()].lower()
        if "as of" in before or "as on" in before:
            continue  # e.g. "CMP as of 11th September, 2026" is a price date, not the report date
        d = parse_date(m.group(0))
        if d:
            cands.append(d)
    distinct = list(dict.fromkeys(cands))
    if len(distinct) == 1:
        return Field(distinct[0], KNOWN)
    header = [d for d in (parse_date(m.group(0)) for m in _DATE_RX.finditer(p2[:200])) if d]
    if len(distinct) > 1 and header and header[0] in distinct:
        return Field(header[0], KNOWN, "confirmed by page-2 running header")
    if not distinct and header:
        return Field(header[0], KNOWN, "from page-2 running header")
    return _single(distinct, "report date", warnings)


def _rating(p1: str, warnings: list[str]) -> tuple[Field, Field]:
    found: list[tuple[str, str]] = []  # (original, core)
    lines = _lines(p1)
    for line in lines[:8]:  # ICICI: "BUY (Maintain)" near the top
        m = re.match(r"^(STRONG BUY|BUY|ADD|HOLD|REDUCE|SELL)\s*(\((?:Maintain|Upgrade|Downgrade|Initiat\w*)\))?(?:\s|$)", line)
        if m:
            found.append((" ".join(x for x in m.groups() if x), m.group(1).upper()))
    for m in re.finditer(r"TP:\s*INR\s*" + _NUM + r"\s*\([+-]?\d+(?:\.\d+)?%\)\s*(Buy|BUY|Neutral|NEUTRAL|Sell|SELL)\b", p1):
        found.append((m.group(2), m.group(2).upper()))  # Motilal Oswal price line
    for i, line in enumerate(lines[:-1]):  # Axis: "BUY" then "Target Price"
        if line.upper() in ("BUY", "HOLD", "SELL", "ACCUMULATE", "REDUCE") and lines[i + 1].lower().startswith("target price"):
            found.append((line, line.upper()))
    cores = list(dict.fromkeys(c for _, c in found))
    if len(cores) == 1:
        original = found[0][0]
        return Field(original, KNOWN), Field(cores[0], KNOWN)
    if len(cores) > 1:
        warnings.append(f"AMBIGUOUS_RATING: {', '.join(cores)}")
        return Field(None, AMBIGUOUS), Field(None, AMBIGUOUS, "more than one rating found")
    return Field(None, UNKNOWN, "rating not found"), Field(None, UNKNOWN, "rating not found")


def _prices(p1: str, warnings: list[str]) -> dict[str, Field]:
    out: dict[str, Field] = {}
    cmps = [parse_decimal(m.group(1)) for m in re.finditer(r"CMP:\s*INR\s*" + _NUM, p1)]
    cmps += [parse_decimal(m.group(1)) for m in re.finditer(r"CMP\s*\(Rs\)\s*" + _NUM, p1)]
    out["report_cmp"] = _single([c for c in cmps if c], "report CMP", warnings)
    asof = re.search(r"CMP as of\s+([^)\n]{6,30})", p1)
    if asof and parse_date(asof.group(1)):
        out["cmp_as_of"] = Field(parse_date(asof.group(1)), KNOWN)

    targets, previous = [], []
    for m in re.finditer(r"Target Price:\s*INR\s*" + _NUM + r"(?:\s*\(INR\s*" + _NUM + r"\))?", p1):
        targets.append(parse_decimal(m.group(1)))
        if m.group(2):
            previous.append(parse_decimal(m.group(2)))
    targets += [parse_decimal(m.group(1)) for m in re.finditer(r"\bTP:\s*INR\s*" + _NUM, p1)]
    targets += [parse_decimal(m.group(1)) for m in re.finditer(r"Target Price\s*\n\s*" + _NUM, p1)]
    targets += [parse_decimal(m.group(1)) for m in re.finditer(r"\bTP of Rs\.?\s*" + _NUM, p1)]
    out["target"] = _single([t for t in targets if t], "target", warnings)
    if previous and previous[0]:
        out["previous_target"] = Field(previous[0], KNOWN, "previous target shown in parentheses; not the current target")
    return out


def _optional_levels(full: str, warnings: list[str]) -> dict[str, Field]:
    out: dict[str, Field] = {}
    entries = re.findall(
        r"(?i)\b(?:entry(?:\s+(?:price|range|zone|level))?|buy\s+(?:range|between|zone))\s*[:\-]?\s*(?:INR|Rs\.?)\s*"
        + _NUM + r"(?:\s*(?:-|–|to)\s*(?:INR|Rs\.?)?\s*" + _NUM + r")?", full)
    if entries:
        lows = list(dict.fromkeys(parse_decimal(a) for a, _ in entries))
        highs = list(dict.fromkeys(parse_decimal(b) if b else parse_decimal(a) for a, b in entries))
        if len(lows) == 1 and len(highs) == 1 and lows[0] and highs[0]:
            out["entry_low"], out["entry_high"] = Field(lows[0], KNOWN), Field(highs[0], KNOWN)
        else:
            warnings.append("AMBIGUOUS_ENTRY: more than one entry level stated")
            out["entry_low"] = out["entry_high"] = Field(None, AMBIGUOUS)
    stops = [parse_decimal(m) for m in re.findall(r"(?i)\bstop[\s-]?loss\s*(?:of|at)?\s*[:\-]?\s*(?:INR|Rs\.?)\s*" + _NUM, full)]
    stops = [s for s in stops if s]
    if stops:
        out["stop_loss"] = _single(stops, "stop loss", warnings)
    return out


def _horizon(full: str, warnings: list[str]) -> Field:
    explicit, legend = [], False
    rx = re.compile(r"(?i)(?:investment|time|holding)\s+horizon\s*(?:of|:|-)?\s*(\d{1,2}(?:\s*(?:-|–|to)\s*\d{1,2})?\s*months?)")
    for m in rx.finditer(full):
        window = full[max(0, m.start() - 200):m.end() + 50].lower()
        if "rating" in window or "expected return" in window:
            legend = True
            continue
        explicit.append(" ".join(m.group(1).split()))
    if re.search(r"(?i)expected (?:absolute )?returns?\s*\(?over\s*\d{1,2}", full) or re.search(r"(?i)refers? to \d{1,2}-month performance horizon", full):
        legend = True
    if explicit:
        return _single(explicit, "time horizon", warnings)
    if legend:
        warnings.append("HORIZON_ONLY_IN_RATING_LEGEND: the report states no horizon for this call; the broker's rating legend defines one generically")
    return Field(None, NOT_STATED, "no explicit horizon for this report")


def _analysts(full: str) -> Field:
    names: list[str] = []
    for m in re.finditer(r"([A-Z][a-z]+(?: [A-Z][a-z]+){1,2})\s*[-–]\s*Research [Aa]nalyst", full):
        names.append(m.group(1))
    for m in re.finditer(r"\b([a-z]+)\.([a-z]+)@icicisecurities\.com", full):
        names.append(f"{m.group(1).title()} {m.group(2).title()}")
    for m in re.finditer(r"([A-Z][a-z]+ [A-Z][a-z]+)\s+Research Analyst\s+[\w.]+@axissecurities", full):
        names.append(m.group(1))
    names = list(dict.fromkeys(names))
    return Field(names, KNOWN) if names else Field([], UNKNOWN, "analyst names not readable")


def _report_type(p1: str) -> Field:
    for rx in (r"India \| Equity Research \| ([A-Za-z ]+?)\s*$",
               r"((?:\dQFY\d\d\s+)?(?:Company Update|Results? Update|Initiating Coverage|Sector Update|Update))\s*\|\s*Sector:",
               r"\b(Company Update|Results? Update|Result Review|Initiating Coverage|Sector Update)\b"):
        for line in _lines(p1):
            m = re.search(rx, line)
            if m:
                return Field(" ".join(m.group(1).split()), KNOWN)
    return Field(None, UNKNOWN, "report type not found")


def _company(p1: str, p2: str) -> Field:
    lines = _lines(p1)
    for i, line in enumerate(lines[:-1]):
        if re.search(r"India \| Equity Research \|", line) or re.search(r"\|\s*Sector:", line):
            cand = lines[i + 1]
            if 2 <= len(cand) <= 60 and not re.search(r"(?i)investors|disclosure|research", cand):
                return Field(cand, KNOWN, "title line")
        if line.lower().startswith("target price") and i + 2 < len(lines) and parse_decimal(lines[i + 1]):
            return Field(lines[i + 2], KNOWN, "title line")
    head = " ".join(p2.split())[:120]
    m = re.match(r"(.{3,60}?)\s+" + _DATE_RX.pattern + r"\s+\d{1,3}\b", head, re.IGNORECASE)
    if m:
        return Field(m.group(1).strip(), KNOWN, "page-2 running header")
    return Field(None, UNKNOWN, "company title not found")


# ---------------------------------------------------------------- entry point

def _base_interpreter() -> str | None:
    """The base Python interpreter, or None if it cannot be trusted.

    On Windows the venv python.exe is a launcher that starts the real interpreter
    as a child process, which could escape the Job Object; the worker must be the
    base interpreter itself.
    """
    base = getattr(sys, "_base_executable", None)
    if not base or not isinstance(base, str):
        return None
    path = Path(base)
    if not path.is_file():
        return None
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    if in_venv and path.resolve() == Path(sys.executable).resolve():
        return None  # only the venv launcher is known
    return str(path)


def _worker_command() -> list[str]:
    """Interpreter command for the worker.

    The base interpreter is started directly. On Windows there is no fallback:
    without a trustworthy base interpreter the PDF is not parsed (PARSER_FAILED).
    pypdf's install folder is passed explicitly and appended after the standard
    library. -I ignores environment variables and the user site; -S keeps the base
    installation's own site-packages out.
    """
    import pypdf

    python = _base_interpreter()
    if python is None:
        if _IS_WINDOWS:
            raise PdfExtractionError.of(PARSER_FAILED)
        python = sys.executable  # POSIX venv interpreters are the real interpreter, not a launcher
    site_dir = str(Path(pypdf.__file__).resolve().parent.parent)
    return [python, "-I", "-S", str(_WORKER_PATH), str(MAX_PAGES), str(MAX_TEXT_CHARS),
            str(WORKER_MEMORY_LIMIT_BYTES), site_dir]


def _process_handle(proc: subprocess.Popen):
    return int(proc._handle)  # Windows process handle owned by Popen


def _create_worker_job():
    from app.services.windows_job import WorkerJob
    return WorkerJob(WORKER_MEMORY_LIMIT_BYTES)


def _terminate(proc: subprocess.Popen, job) -> None:
    """Kill the worker; on Windows the Job Object kills the whole process tree."""
    if job is not None:
        try:
            job.terminate()
        except Exception:  # noqa: BLE001 - still kill the process directly below
            pass
    try:
        proc.kill()
    except OSError:
        pass


def _failure_category(result: Any, proc: subprocess.Popen, peak_memory: int | None) -> str:
    if isinstance(result, dict):
        return {"RESOURCE_LIMIT": RESOURCE_LIMIT, "UNREADABLE": UNREADABLE_PDF}.get(result.get("error"), PARSER_FAILED)
    # No usable answer: the worker died. Distinguish a memory kill from a broken worker.
    if peak_memory is not None and peak_memory >= WORKER_MEMORY_LIMIT_BYTES * 0.9:
        return RESOURCE_LIMIT
    if not _IS_WINDOWS and proc.returncode == -getattr(signal, "SIGKILL", 9):
        return RESOURCE_LIMIT  # POSIX out-of-memory kill
    return PARSER_FAILED


def read_pdf_pages_isolated(content: bytes) -> tuple[list[str], bool, bool]:
    """Read page text in a separate, killable, memory-limited process.

    Returns (page texts, encrypted, page limit reached). Raises PdfExtractionError
    with a client-safe message and category on timeout, resource limit, busy
    parser, unreadable file or parser failure.
    """
    if not _PARSE_SLOTS.acquire(timeout=PARSE_TIMEOUT_SECONDS):
        raise PdfExtractionError.of(BUSY)
    job = None
    try:
        try:
            proc = subprocess.Popen(
                _worker_command(),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError:
            raise PdfExtractionError.of(PARSER_FAILED) from None
        peak_memory = None
        try:
            if _IS_WINDOWS:
                # The worker waits for the PDF on stdin, so the limit is in place
                # before any parsing starts. No containment -> no parsing.
                try:
                    job = _create_worker_job()
                    job.assign(_process_handle(proc))
                except Exception:  # any ordinary setup failure; KeyboardInterrupt/SystemExit propagate
                    _terminate(proc, job)
                    proc.communicate()  # no PDF bytes are ever sent to an uncontained worker
                    raise PdfExtractionError.of(PARSER_FAILED) from None
            try:
                out, _ = proc.communicate(content, timeout=PARSE_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                _terminate(proc, job)
                proc.communicate()
                raise PdfExtractionError.of(TIMEOUT) from None
            if job is not None:
                peak_memory = job.peak_process_memory()
        finally:
            if proc.poll() is None:  # never leave a parser behind
                _terminate(proc, job)
                proc.wait()
            if job is not None:
                job.close()  # KILL_ON_JOB_CLOSE ends anything still in the job
    finally:
        _PARSE_SLOTS.release()
    try:
        result = json.loads(out.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        result = None
    if isinstance(result, dict) and result.get("ok") is True and isinstance(result.get("pages"), list):
        return [str(p) for p in result["pages"]], bool(result.get("encrypted")), bool(result.get("page_limit_reached"))
    raise PdfExtractionError.of(_failure_category(result, proc, peak_memory))


def extract_fields(content: bytes) -> Extraction:
    """In-process extraction (trusted callers and tests)."""
    pages, encrypted = read_pdf_pages(content)
    return fields_from_pages(pages, encrypted)


def extract_fields_isolated(content: bytes) -> Extraction:
    """Extraction for untrusted uploads: the PDF is parsed in a killable subprocess."""
    pages, encrypted, limit_reached = read_pdf_pages_isolated(content)
    ex = fields_from_pages(pages, encrypted)
    if limit_reached:
        ex.warnings.append(f"PAGE_LIMIT: only the first {MAX_PAGES} pages were read")
    return ex


def fields_from_pages(pages: list[str], encrypted: bool) -> Extraction:
    ex = Extraction(page_count=len(pages))
    if encrypted:
        ex.warnings.append("ENCRYPTED_PDF: text cannot be extracted; enter values from the visible PDF")
        return ex
    full = "\n".join(pages)
    ex.text_chars = len(full.strip())
    if ex.text_chars < 200:
        ex.warnings.append("LITTLE_OR_NO_TEXT: the PDF may be scanned images; enter values from the visible PDF")
    p1 = pages[0] if pages else ""
    p2 = pages[1] if len(pages) > 1 else ""

    w = ex.warnings
    ex.broker = _broker(full, w)
    ex.report_type = _report_type(p1)
    ex.company_name = _company(p1, p2)
    bb = list(dict.fromkeys(re.findall(r"Bloomberg\s+([A-Z0-9&-]{2,12})\s+IN\b", p1)))
    if len(bb) == 1:
        ex.bloomberg_code = Field(bb[0] + " IN", KNOWN)
    ex.report_date = _report_date(p1, p2, w)
    ex.original_rating, ex.rating_core = _rating(p1, w)
    for k, v in _prices(p1, w).items():
        setattr(ex, k, v)
    for k, v in _optional_levels(full, w).items():
        setattr(ex, k, v)
    ex.time_horizon = _horizon(full, w)
    ex.analysts = _analysts(full)

    if ex.cmp_as_of.status == KNOWN and ex.report_date.status == KNOWN and ex.cmp_as_of.value != ex.report_date.value:
        w.append(f"CMP_DATE_DIFFERS: report CMP is as of {ex.cmp_as_of.value.isoformat()}, report dated {ex.report_date.value.isoformat()}")
    if ex.previous_target.status == KNOWN:
        w.append(f"TARGET_REVISED: previous target {format(ex.previous_target.value, 'f')} shown in parentheses")
    if ex.stop_loss.status == NOT_STATED:
        w.append("NO_STOP_LOSS_STATED: stop loss stays empty")
    if ex.entry_low.status == NOT_STATED:
        w.append("NO_ENTRY_RANGE_STATED: entry range stays empty; the report CMP is not an entry price")
    return ex
