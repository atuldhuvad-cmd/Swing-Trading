"""Preview-first intake of broker research PDFs.

``preview_pdf`` is strictly read-only: it validates and hashes the file, reads
its text, maps broker/stock/rating to existing master data and compares the
result with stored recommendations. It never stores the PDF, never writes the
manifest and never writes the database. Confirming anything is a separate,
explicitly authorised step.

Source policy: the broker-authored PDF is the canonical evidence
(``BROKER_RESEARCH``, publication = the broker). A discovery platform such as
Trendlyne is recorded separately as ``discovery_source``. ``VERIFIED_PRIMARY``
is only *proposed*; it becomes real after the visible PDF is checked.

Preview actions
  NEW                        no equivalent recommendation; a new one may be created
  NEW_REVISION               newer report than the CURRENT one for this stock+broker;
                             may supersede it, keeping history
  ATTACH_SOURCE              complete match (see below); attach this PDF as primary
                             evidence, create nothing
  EXACT_DUPLICATE            complete match, and a source linked to that recommendation
                             already carries this exact PDF (same document_sha256)
  CONFLICT_REVIEW_REQUIRED   same identity but a stated field (CMP, target, entry, stop,
                             horizon or rating) differs; nothing is attached or overwritten
  UNKNOWN_STOCK              company is not in stock_master; archive only
  UNKNOWN_BROKER             broker not identified or not in broker_master; review only
  REVIEW_REQUIRED            a required field is missing/ambiguous, a stored field is not
                             stated in the report, the PDF is already linked to another
                             recommendation, or the report is older than the CURRENT one

Complete match: stock, broker, report date, normalized rating, report CMP and target
are all KNOWN in the report and equal to the stored recommendation. Optional fields
(entry low/high, stop loss, horizon) must match when both sides state them; an
ambiguous optional field, or a stored optional field the report does not state
(UNSTATED_STORED_FIELD), needs review. Missing values are never filled in.
``duplicate_file`` is reported separately: a byte-identical PDF is stored only once.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    BrokerMaster, BrokerRecommendation, RatingNormalization, RecommendationSource,
    SourceReference, SourceTypeMaster, StockMaster,
)
from app.services import broker_upload_service as uploads
from app.services.broker_pdf_extraction import (
    AMBIGUOUS, KNOWN, NOT_STATED, UNKNOWN, Extraction, PdfExtractionError, extract_fields_isolated,
)

class PdfReadFailure(uploads.BrokerUploadError):
    """The PDF could not be read; ``category`` comes from the isolated parser."""

    def __init__(self, message: str, category: str):
        super().__init__(message)
        self.category = category


CANONICAL_SOURCE_TYPE = "BROKER_RESEARCH"
PROPOSED_VERIFICATION = "VERIFIED_PRIMARY"
VERIFICATION_STATE = "PENDING_VISUAL_CONFIRMATION"

MANDATORY_REPORT_FIELDS = ("report_cmp", "target")
OPTIONAL_REPORT_FIELDS = ("entry_low", "entry_high", "stop_loss", "time_horizon")

_SUFFIXES = {"ltd", "limited", "co", "company", "corp", "corporation", "inc", "plc", "the"}
_PRICE_TOLERANCE = Decimal("0.005")


def _norm_name(name: str | None) -> tuple[str, ...]:
    words = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower()).split()
    return tuple(w for w in words if w not in _SUFFIXES)


def _dec(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:  # noqa: BLE001
        return None


def _same_price(a: Any, b: Any) -> bool:
    da, db = _dec(a), _dec(b)
    return da is not None and db is not None and abs(da - db) <= _PRICE_TOLERANCE


def _fmt(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return format(v, "f")
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


def _match_stock(db: Session, ex: Extraction, hint: str | None, warnings: list[str]) -> tuple[StockMaster | None, str]:
    by_title = None
    if ex.company_name.status == KNOWN:
        title = _norm_name(ex.company_name.value)
        hits = [s for s in db.query(StockMaster).all() if title and _norm_name(s.company_name) == title]
        if len(hits) == 1:
            by_title = hits[0]
        elif len(hits) > 1:
            warnings.append(f"AMBIGUOUS_STOCK: {', '.join(s.nse_symbol for s in hits)}")
            return None, AMBIGUOUS
    hint = (hint or "").strip().upper() or None
    if hint:
        hinted = db.query(StockMaster).filter(StockMaster.nse_symbol == hint).first()
        if hinted is None:
            warnings.append(f"SYMBOL_HINT_NOT_IN_STOCK_MASTER: {hint}")
            return None, UNKNOWN
        if by_title and by_title.stock_id != hinted.stock_id:
            warnings.append(f"SYMBOL_HINT_CONFLICT: report title matches {by_title.nse_symbol}, hint was {hint}")
            return None, AMBIGUOUS
        if not by_title:
            warnings.append(f"STOCK_FROM_SYMBOL_HINT: {hint} (report title not matched automatically)")
        return hinted, KNOWN
    return (by_title, KNOWN) if by_title else (None, UNKNOWN)


def _normalized_rating(db: Session, ex: Extraction) -> str | None:
    if ex.rating_core.status != KNOWN:
        return None
    mapping = {r.original_rating.strip().lower(): r.normalized_rating for r in db.query(RatingNormalization).all()}
    for key in (str(ex.original_rating.value or "").strip().lower(), ex.rating_core.value.lower()):
        if key in mapping:
            return mapping[key]
    return None


def _economic_diffs(ex: Extraction, rec: BrokerRecommendation) -> tuple[list[dict[str, Any]], list[str]]:
    """Fields stated on both sides that differ, and fields the report does not state."""
    diffs, unstated = [], []

    def compare(name: str, report_field, stored, same) -> None:
        if report_field.status == KNOWN and stored is not None:
            if not same(report_field.value, stored):
                diffs.append({"field": name, "report": _fmt(report_field.value), "stored": _fmt(stored)})
        elif report_field.status == KNOWN and stored is None:
            diffs.append({"field": name, "report": _fmt(report_field.value), "stored": None})
        elif report_field.status in (NOT_STATED, UNKNOWN) and stored is not None:
            unstated.append(f"{name} stored as {_fmt(stored)} but not stated in this report")

    compare("report_cmp (recommended_price)", ex.report_cmp, rec.recommended_price, _same_price)
    compare("target", ex.target, rec.target_price, _same_price)
    compare("entry_low", ex.entry_low, rec.entry_price_low, _same_price)
    compare("entry_high", ex.entry_high, rec.entry_price_high, _same_price)
    compare("stop_loss", ex.stop_loss, rec.stop_loss, _same_price)
    compare("time_horizon", ex.time_horizon, rec.time_horizon_text,
            lambda a, b: re.sub(r"\W", "", str(a).lower()) == re.sub(r"\W", "", str(b).lower()))
    return diffs, unstated


def _recommendations_linked_to_document(db: Session, sha: str) -> set[int]:
    """Recommendations whose linked source carries exactly this PDF."""
    rows = db.query(RecommendationSource.recommendation_id).join(
        SourceReference, RecommendationSource.source_reference_id == SourceReference.source_reference_id
    ).filter(SourceReference.document_sha256 == sha).all()
    return {r[0] for r in rows}


def _has_primary_research(db: Session, rec_id: int) -> bool:
    return db.query(SourceReference).join(
        RecommendationSource, RecommendationSource.source_reference_id == SourceReference.source_reference_id
    ).join(SourceTypeMaster, SourceTypeMaster.source_type_id == SourceReference.source_type_id).filter(
        RecommendationSource.recommendation_id == rec_id,
        SourceTypeMaster.type_name == CANONICAL_SOURCE_TYPE,
        SourceReference.verification_status == PROPOSED_VERIFICATION,
    ).count() > 0


def _rec_summary(rec: BrokerRecommendation) -> dict[str, Any]:
    return {
        "recommendation_id": rec.recommendation_id,
        "recommendation_date": _fmt(rec.recommendation_date.date() if rec.recommendation_date else None),
        "original_rating": rec.original_rating,
        "normalized_rating": rec.normalized_rating,
        "recommended_price": _fmt(rec.recommended_price),
        "entry_price_low": _fmt(rec.entry_price_low),
        "entry_price_high": _fmt(rec.entry_price_high),
        "target_price": _fmt(rec.target_price),
        "stop_loss": _fmt(rec.stop_loss),
        "time_horizon_text": rec.time_horizon_text,
        "lifecycle_status": rec.lifecycle_status,
    }


def preview_pdf(
    db: Session,
    *,
    content: bytes,
    original_filename: str,
    content_type: str | None = "application/pdf",
    stock_symbol_hint: str | None = None,
    discovery_source: str | None = None,
    discovery_url: str | None = None,
    batch_seen_sha256: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Non-persistent preview of one PDF. Raises BrokerUploadError for invalid files."""
    safe_name = uploads.validate_pdf(original_filename, content, content_type)
    source, url = uploads.validate_discovery(discovery_source, discovery_url)
    sha = uploads.sha256_hex(content)

    stored = uploads.find_by_sha256(sha)
    in_batch = (batch_seen_sha256 or {}).get(sha)
    file_info = {
        "original_filename": original_filename,
        "safe_filename": safe_name,
        "size_bytes": len(content),
        "sha256": sha,
        "duplicate_file": bool(stored or in_batch),
        "duplicate_of_upload_id": stored.get("upload_id") if stored else None,
        "duplicate_of_batch_file": in_batch,
    }
    result: dict[str, Any] = {
        "file": file_info,
        "discovery": {
            "discovery_source": source,
            "discovery_url": url,
            "discovery_url_status": "PROVIDED" if url else "UNAVAILABLE",
        },
        "canonical_source": {
            "source_type": CANONICAL_SOURCE_TYPE,
            "publication_name": None,
            "proposed_verification_status": None,
            "verification_state": VERIFICATION_STATE,
        },
        "persisted": False,
    }
    if in_batch:
        result.update({"action": "DUPLICATE_FILE", "extraction": None, "warnings": [f"DUPLICATE_FILE: byte-identical to {in_batch} in this batch"]})
        return result

    try:
        ex = extract_fields_isolated(content)
    except PdfExtractionError as exc:
        raise PdfReadFailure(str(exc), exc.category) from None
    warnings = list(ex.warnings)
    result["extraction"] = ex.as_dict()

    broker = None
    if ex.broker.status == KNOWN:
        broker = db.query(BrokerMaster).filter(BrokerMaster.canonical_name == ex.broker.value).first()
        if broker is None:
            warnings.append(f"BROKER_NOT_IN_BROKER_MASTER: {ex.broker.value}")
    result["broker"] = {"name": ex.broker.value, "broker_id": broker.broker_id if broker else None}
    result["canonical_source"]["publication_name"] = broker.canonical_name if broker else ex.broker.value

    stock, stock_status = _match_stock(db, ex, stock_symbol_hint, warnings)
    result["stock"] = {
        "company_name": ex.company_name.value,
        "nse_symbol": stock.nse_symbol if stock else None,
        "stock_id": stock.stock_id if stock else None,
        "status": stock_status,
    }
    normalized = _normalized_rating(db, ex)
    if ex.rating_core.status == KNOWN and normalized is None:
        warnings.append(f"UNMAPPED_RATING: {ex.original_rating.value}")
    result["rating"] = {"original": ex.original_rating.value, "normalized": normalized}

    required_ok = (ex.report_date.status == KNOWN and normalized is not None)
    if broker and required_ok and ex.target.status == KNOWN and ex.report_cmp.status == KNOWN:
        result["canonical_source"]["proposed_verification_status"] = PROPOSED_VERIFICATION
    elif broker:
        result["canonical_source"]["proposed_verification_status"] = "PROVISIONAL"
    for name in ("report_cmp", "target"):
        if getattr(ex, name).status != KNOWN:
            warnings.append(f"MISSING_{name.upper()}: {getattr(ex, name).status}")

    existing, action, supersedes, diffs, unstated = None, None, None, [], []
    selected_id, candidate_ids = None, []
    linked_recs = _recommendations_linked_to_document(db, sha)
    if broker is None:
        action = "UNKNOWN_BROKER"
    elif stock is None:
        action = "UNKNOWN_STOCK" if stock_status == UNKNOWN else "REVIEW_REQUIRED"
    elif not required_ok or any(getattr(ex, f).status == AMBIGUOUS for f in MANDATORY_REPORT_FIELDS + OPTIONAL_REPORT_FIELDS):
        action = "REVIEW_REQUIRED"
        for f in OPTIONAL_REPORT_FIELDS:
            if getattr(ex, f).status == AMBIGUOUS:
                warnings.append(f"AMBIGUOUS_OPTIONAL_FIELD: {f}")
    else:
        same_day = sorted((r for r in db.query(BrokerRecommendation).filter(
            BrokerRecommendation.stock_id == stock.stock_id, BrokerRecommendation.broker_id == broker.broker_id,
        ).all() if r.recommendation_date and r.recommendation_date.date() == ex.report_date.value),
            key=lambda r: r.recommendation_id)
        same_rating = [r for r in same_day if r.normalized_rating == normalized]
        if len(same_rating) > 1:
            # Never pick one of several equivalent records silently.
            action = "REVIEW_REQUIRED"
            candidate_ids = [r.recommendation_id for r in same_rating]
            warnings.append(f"MULTIPLE_SAME_DAY_MATCHES: recommendations {', '.join(map(str, candidate_ids))}")
        elif same_day:
            rec = same_rating[0] if same_rating else same_day[0]
            selected_id = rec.recommendation_id
            existing = _rec_summary(rec)
            if rec.normalized_rating != normalized:
                diffs = [{"field": "normalized_rating", "report": normalized, "stored": rec.normalized_rating}]
            else:
                diffs, unstated = _economic_diffs(ex, rec)
            missing = [f for f in MANDATORY_REPORT_FIELDS if getattr(ex, f).status != KNOWN]
            if diffs:
                action = "CONFLICT_REVIEW_REQUIRED"
            elif missing or unstated:
                action = "REVIEW_REQUIRED"
                warnings.extend(f"MISSING_MANDATORY_FIELD: {f} is not stated in this report" for f in missing)
                warnings.extend(f"UNSTATED_STORED_FIELD: {u}" for u in unstated)
            elif linked_recs == {rec.recommendation_id}:
                action = "EXACT_DUPLICATE"
            else:
                action = "ATTACH_SOURCE"
                if _has_primary_research(db, rec.recommendation_id):
                    warnings.append("RECOMMENDATION_ALREADY_HAS_BROKER_RESEARCH_EVIDENCE: confirm this PDF is a different document before attaching")
        else:
            current = db.query(BrokerRecommendation).filter(
                BrokerRecommendation.stock_id == stock.stock_id, BrokerRecommendation.broker_id == broker.broker_id,
                BrokerRecommendation.lifecycle_status == "CURRENT",
            ).order_by(BrokerRecommendation.recommendation_date.desc()).first()
            if current is None:
                action = "NEW"
            elif current.recommendation_date.date() < ex.report_date.value:
                action, supersedes, existing = "NEW_REVISION", current.recommendation_id, _rec_summary(current)
            else:
                action, existing = "REVIEW_REQUIRED", _rec_summary(current)
                warnings.append("OLDER_THAN_CURRENT_RECOMMENDATION: a newer call from this broker is already CURRENT")

    # A PDF linked to any recommendation other than the selected same-day match
    # always needs review (a conflict stays a conflict); the warning is never dropped.
    other_links = sorted(linked_recs - {selected_id})
    if other_links:
        if action != "CONFLICT_REVIEW_REQUIRED":
            action = "REVIEW_REQUIRED"
        warnings.append(f"DOCUMENT_ALREADY_LINKED: this exact PDF is already evidence for recommendation(s) {', '.join(map(str, other_links))}")
    if action == "EXACT_DUPLICATE" and not stored:
        warnings.append("LINKED_PDF_NOT_IN_LOCAL_UPLOADS: the recommendation cites this PDF but no local copy is stored")
    if file_info["duplicate_file"]:
        warnings.append(f"DUPLICATE_FILE: identical PDF already stored as upload {file_info['duplicate_of_upload_id']}")
    result.update({
        "action": action,
        "document_linked_recommendation_ids": sorted(linked_recs),
        "candidate_recommendation_ids": candidate_ids,
        "existing_match": existing,
        "supersedes_recommendation_id": supersedes,
        "differences": diffs,
        "not_stated_in_report": unstated,
        "proposed_recommendation": None if action not in ("NEW", "NEW_REVISION") else {
            "stock_id": stock.stock_id, "broker_id": broker.broker_id,
            "recommendation_date": _fmt(ex.report_date.value),
            "original_rating": ex.original_rating.value, "normalized_rating": normalized,
            "recommended_price": _fmt(ex.report_cmp.value) if ex.report_cmp.status == KNOWN else None,
            "entry_price_low": _fmt(ex.entry_low.value) if ex.entry_low.status == KNOWN else None,
            "entry_price_high": _fmt(ex.entry_high.value) if ex.entry_high.status == KNOWN else None,
            "target_price": _fmt(ex.target.value) if ex.target.status == KNOWN else None,
            "stop_loss": _fmt(ex.stop_loss.value) if ex.stop_loss.status == KNOWN else None,
            "time_horizon_text": ex.time_horizon.value if ex.time_horizon.status == KNOWN else None,
            "analyst_name": ", ".join(ex.analysts.value) if ex.analysts.status == KNOWN else None,
            "currency": "INR",
        },
        "warnings": warnings,
    })
    return result
