"""Broker research PDF intake: extraction, duplicate/conflict policy and non-persistence.

All PDFs here are synthetic (tests/pdf_factory.py); no real broker report is stored in the repo.
"""
import hashlib
import json
from datetime import datetime

import pytest

from app.models import (
    BrokerMaster, BrokerRecommendation, RatingNormalization, RecommendationSource,
    SourceReference, SourceTypeMaster, StockMaster,
)
from app.services import broker_upload_service as uploads
from app.services.broker_pdf_extraction import extract_fields
from app.services.broker_pdf_intake_service import preview_pdf
from tests.pdf_factory import make_pdf


# ---------------------------------------------------------------- synthetic reports

def motilal(cmp="3,105", tp="3,880", rating="Buy", day="9 September 2026", company="Adani Enterprises", extra=()):
    return make_pdf([
        [day, "Company Update | Sector: Infrastructure", company,
         "Investors are advised to refer through important disclosures made at the last page of the Research Report.",
         "Motilal Oswal research is available on www.motilaloswal.com/Institutional-Equities",
         "Asha Example - Research analyst (Asha.Example@MotilalOswal.com)",
         f"CMP: INR{cmp} TP: INR{tp} (+25%) {rating}", "Bloomberg ADE IN", *extra],
        [f"{company} {day} 2", "Explanation of Investment Rating Expected return (over 12-month) BUY >=15%",
         "Motilal Oswal Financial Services Limited"],
    ])


def icici(cmp="720", tp="920", prev="1,020", day="31 August 2026", company="HDFC Bank"):
    tp_text = f"Target Price: INR {tp} (INR {prev})" if prev else f"Target Price: INR {tp}"
    return make_pdf([
        ["Please refer to important disclosures at the end of this report", "BUY (Maintain)",
         f"CMP: INR {cmp} {tp_text} 28% ICICI Securities Limited is the author and distributor of this report",
         f"{day} India | Equity Research | Company Update", company, "Banking",
         "Ravi Sample ravi.sample@icicisecurities.com"],
        ["All ratings and target price refers to 12-month performance horizon, unless mentioned otherwise",
         "ICICI Securities Limited SEBI Registration INZ000183631"],
    ])


def axis(company="Coforge Ltd."):
    return make_pdf([
        ["Company Update", "15th September, 2026", "BUY", "Target Price", "2,275", company, "IT Services Sector",
         "We value the company with an Unchanged TP of Rs 2,275/share, implying an upside of 23% from the CMP.",
         "(CMP as of 11th September, 2026)", "CMP (Rs) 1,847",
         "Neel Testcase Research Analyst neel.testcase@axissecurities.in"],
        ["Axis Securities Limited", "Ratings Expected absolute returns over 12 - 18 months BUY More than 10%"],
    ])


# ---------------------------------------------------------------- fixtures

@pytest.fixture
def intake_env(db_session, monkeypatch, tmp_path):
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(uploads, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(uploads, "MANIFEST_PATH", upload_dir / "manifest.json")
    monkeypatch.setattr(uploads, "BASE_DIR", tmp_path)
    for name in ("Motilal Oswal", "ICICI Securities", "Axis Securities"):
        db_session.add(BrokerMaster(display_name=name, canonical_name=name, normalized_name=name.lower()))
    for sym, name in (("ADANIENT", "Adani Enterprises Ltd."), ("HDFCBANK", "HDFC Bank Ltd."),
                      ("INDIGO", "InterGlobe Aviation Limited")):
        db_session.add(StockMaster(nse_symbol=sym, company_name=name))
    db_session.add(RatingNormalization(original_rating="Buy", normalized_rating="BUY"))
    db_session.commit()
    return db_session


def ids(db, sym=None, broker=None):
    stock = db.query(StockMaster).filter_by(nse_symbol=sym).one() if sym else None
    b = db.query(BrokerMaster).filter_by(canonical_name=broker).one() if broker else None
    return stock, b


def add_rec(db, sym, broker, day, *, cmp, tp, entry=None, stop=None, horizon=None, research=False,
            sha=None, rating="BUY", status="CURRENT"):
    stock, b = ids(db, sym, broker)
    rec = BrokerRecommendation(stock_id=stock.stock_id, broker_id=b.broker_id,
                               recommendation_date=datetime.fromisoformat(day), original_rating=rating,
                               normalized_rating=rating, recommended_price=cmp, target_price=tp,
                               entry_price_low=entry, entry_price_high=entry, stop_loss=stop,
                               time_horizon_text=horizon, lifecycle_status=status)
    db.add(rec)
    db.flush()
    if research or sha:
        st = db.query(SourceTypeMaster).filter_by(type_name="BROKER_RESEARCH").one()
        src = SourceReference(source_type_id=st.source_type_id, publication_name=broker,
                              verification_status="VERIFIED_PRIMARY", document_sha256=sha)
        db.add(src)
        db.flush()
        db.add(RecommendationSource(recommendation_id=rec.recommendation_id, source_reference_id=src.source_reference_id))
    db.commit()
    return rec


def preview(db, content, name="report.pdf", **kw):
    return preview_pdf(db, content=content, original_filename=name, **kw)


# ---------------------------------------------------------------- extraction per broker

def test_motilal_report_fields_and_new_recommendation(intake_env):
    r = preview(intake_env, motilal(), discovery_source="Trendlyne")
    ex = r["extraction"]
    assert r["action"] == "NEW"
    assert ex["broker"]["value"] == "Motilal Oswal"
    assert ex["report_date"]["value"] == "2026-09-09"
    assert (ex["original_rating"]["value"], r["rating"]["normalized"]) == ("Buy", "BUY")
    assert (ex["report_cmp"]["value"], ex["target"]["value"]) == ("3105", "3880")
    assert ex["analysts"]["value"] == ["Asha Example"]
    assert r["stock"]["nse_symbol"] == "ADANIENT"
    src = r["canonical_source"]
    assert (src["source_type"], src["publication_name"], src["proposed_verification_status"], src["verification_state"]) == (
        "BROKER_RESEARCH", "Motilal Oswal", "VERIFIED_PRIMARY", "PENDING_VISUAL_CONFIRMATION")
    assert r["discovery"] == {"discovery_source": "Trendlyne", "discovery_url": None, "discovery_url_status": "UNAVAILABLE"}
    prop = r["proposed_recommendation"]
    assert prop["recommended_price"] == "3105" and prop["target_price"] == "3880"
    assert prop["entry_price_low"] is None and prop["stop_loss"] is None and prop["time_horizon_text"] is None
    assert r["persisted"] is False


def test_icici_report_keeps_revised_target_separate_from_previous(intake_env):
    ex = extract_fields(icici())
    assert (ex.report_cmp.value, ex.target.value, ex.previous_target.value) == (720, 920, 1020)
    assert ex.original_rating.value == "BUY (Maintain)" and ex.rating_core.value == "BUY"
    assert ex.broker.value == "ICICI Securities" and ex.company_name.value == "HDFC Bank"
    assert any(w.startswith("TARGET_REVISED") for w in ex.warnings)
    assert ex.analysts.value == ["Ravi Sample"]


def test_axis_report_flags_cmp_date_that_differs_from_report_date(intake_env):
    r = preview(intake_env, axis())
    ex = r["extraction"]
    assert ex["broker"]["value"] == "Axis Securities"
    assert (ex["report_date"]["value"], ex["cmp_as_of"]["value"]) == ("2026-09-15", "2026-09-11")
    assert (ex["report_cmp"]["value"], ex["target"]["value"]) == ("1847", "2275")
    assert any(w.startswith("CMP_DATE_DIFFERS") for w in r["warnings"])
    assert r["action"] == "UNKNOWN_STOCK"  # Coforge is not in stock_master


# ---------------------------------------------------------------- duplicate / match / conflict policy

def test_sha_identical_files_are_duplicate_in_batch_and_against_the_store(intake_env):
    content = motilal()
    sha = hashlib.sha256(content).hexdigest()
    in_batch = preview(intake_env, content, "copy (1).pdf", batch_seen_sha256={sha: "original.pdf"})
    assert in_batch["action"] == "DUPLICATE_FILE" and in_batch["file"]["duplicate_of_batch_file"] == "original.pdf"

    stored = uploads.save_upload(broker_name="Motilal Oswal", original_filename="a.pdf", content=content,
                                 content_type="application/pdf")
    again = preview(intake_env, content)
    assert again["file"]["duplicate_file"] is True and again["file"]["duplicate_of_upload_id"] == stored["upload_id"]
    with pytest.raises(uploads.DuplicateUploadError):
        uploads.save_upload(broker_name="Motilal Oswal", original_filename="b.pdf", content=content,
                            content_type="application/pdf")


def test_exact_match_proposes_source_attachment_only(intake_env):
    add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=720, tp=920)
    r = preview(intake_env, icici())
    assert r["action"] == "ATTACH_SOURCE" and r["differences"] == [] and r["proposed_recommendation"] is None
    assert r["existing_match"]["recommendation_id"]


def test_exact_duplicate_requires_this_pdf_linked_to_the_recommendation(intake_env):
    content = icici()
    uploads.save_upload(broker_name="ICICI Securities", original_filename="x.pdf", content=content,
                        content_type="application/pdf")
    rec = add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=720, tp=920,
                  sha=hashlib.sha256(content).hexdigest())
    r = preview(intake_env, content)
    assert r["action"] == "EXACT_DUPLICATE"
    assert r["document_linked_recommendation_ids"] == [rec.recommendation_id]


def test_linked_pdf_without_local_copy_is_still_exact_duplicate_with_warning(intake_env):
    content = icici()
    add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=720, tp=920,
            sha=hashlib.sha256(content).hexdigest())
    r = preview(intake_env, content)
    assert r["action"] == "EXACT_DUPLICATE"
    assert any(w.startswith("LINKED_PDF_NOT_IN_LOCAL_UPLOADS") for w in r["warnings"])


def test_stored_pdf_and_unrelated_primary_source_are_not_exact_duplicate(intake_env):
    content = icici()
    # Archived under an unrelated label, never linked; the recommendation's evidence is another document.
    uploads.save_upload(broker_name="Other Broker", stock_symbol="RELIANCE", original_filename="x.pdf",
                        content=content, content_type="application/pdf")
    add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=720, tp=920, research=True)
    r = preview(intake_env, content)
    assert r["action"] == "ATTACH_SOURCE" and r["file"]["duplicate_file"] is True
    assert any(w.startswith("RECOMMENDATION_ALREADY_HAS_BROKER_RESEARCH_EVIDENCE") for w in r["warnings"])


def test_source_linked_to_a_different_pdf_is_not_exact_duplicate(intake_env):
    add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=720, tp=920, sha="0" * 64)
    assert preview(intake_env, icici())["action"] == "ATTACH_SOURCE"


def test_pdf_already_linked_to_another_recommendation_needs_review(intake_env):
    content = motilal()
    other = add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=720, tp=920,
                    sha=hashlib.sha256(content).hexdigest())
    r = preview(intake_env, content)  # would otherwise be NEW for ADANIENT / Motilal Oswal
    assert r["action"] == "REVIEW_REQUIRED" and r["proposed_recommendation"] is None
    assert any(w.startswith("DOCUMENT_ALREADY_LINKED") and str(other.recommendation_id) in w for w in r["warnings"])


def test_economic_conflict_for_same_identity_requires_review_and_writes_nothing(intake_env):
    rec = add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=709.6, tp=925, entry=725)
    before = intake_env.query(RecommendationSource).count(), intake_env.query(SourceReference).count()
    r = preview(intake_env, icici())
    assert r["action"] == "CONFLICT_REVIEW_REQUIRED"
    assert {d["field"] for d in r["differences"]} == {"report_cmp (recommended_price)", "target"}
    assert any("entry_low stored as 725" in s for s in r["not_stated_in_report"])
    intake_env.refresh(rec)
    assert (rec.recommended_price, rec.target_price) == (709.6, 925)
    assert (intake_env.query(RecommendationSource).count(), intake_env.query(SourceReference).count()) == before


def test_newer_report_is_a_revision_and_older_report_needs_review(intake_env):
    old = add_rec(intake_env, "ADANIENT", "Motilal Oswal", "2026-08-01", cmp=3000, tp=3500)
    r = preview(intake_env, motilal())
    assert r["action"] == "NEW_REVISION" and r["supersedes_recommendation_id"] == old.recommendation_id
    older = preview(intake_env, motilal(day="1 July 2026"))
    assert older["action"] == "REVIEW_REQUIRED"
    assert any(w.startswith("OLDER_THAN_CURRENT") for w in older["warnings"])


def test_unknown_stock_is_archive_only(intake_env):
    r = preview(intake_env, motilal(company="Max Healthcare"))
    assert r["action"] == "UNKNOWN_STOCK" and r["stock"]["nse_symbol"] is None
    assert r["proposed_recommendation"] is None
    assert intake_env.query(StockMaster).filter_by(company_name="Max Healthcare").count() == 0


def test_unknown_broker_is_review_only(intake_env):
    content = make_pdf([["9 September 2026", "Company Update | Sector: Infrastructure", "Adani Enterprises",
                         "CMP: INR3,105 TP: INR3,880 (+25%) Buy"]])
    r = preview(intake_env, content)
    assert r["action"] == "UNKNOWN_BROKER" and r["broker"]["broker_id"] is None


# ---------------------------------------------------------------- missing and ambiguous values

def test_missing_target_stays_unknown_and_is_not_verified_primary(intake_env):
    content = make_pdf([["9 September 2026", "Company Update | Sector: Infrastructure", "Adani Enterprises",
                         "Motilal Oswal research is available on www.motilaloswal.com",
                         "Rating: Buy", "Motilal Oswal Financial Services"]])
    r = preview(intake_env, content)
    assert r["extraction"]["target"]["status"] == "UNKNOWN"
    assert r["action"] == "REVIEW_REQUIRED"  # rating not in a recognised position either
    assert any(w.startswith("MISSING_TARGET") for w in r["warnings"])
    assert r["canonical_source"]["proposed_verification_status"] == "PROVISIONAL"


def test_missing_stop_loss_and_horizon_stay_empty(intake_env):
    ex = extract_fields(motilal())
    assert (ex.stop_loss.status, ex.stop_loss.value) == ("NOT_STATED", None)
    assert (ex.time_horizon.status, ex.time_horizon.value) == ("NOT_STATED", None)
    assert (ex.entry_low.status, ex.entry_high.status) == ("NOT_STATED", "NOT_STATED")
    assert any(w.startswith("HORIZON_ONLY_IN_RATING_LEGEND") for w in ex.warnings)


def test_explicitly_stated_stop_entry_and_horizon_are_read(intake_env):
    ex = extract_fields(motilal(extra=("Entry range: INR 3,050 - INR 3,100", "Stop loss: INR 2,900",
                                       "Investment horizon: 3 months")))
    assert (ex.entry_low.value, ex.entry_high.value, ex.stop_loss.value) == (3050, 3100, 2900)
    assert ex.time_horizon.value == "3 months"


def test_ambiguous_prices_require_review(intake_env):
    content = motilal(extra=("CMP: INR3,250 TP: INR3,880 (+19%) Buy",))
    r = preview(intake_env, content)
    assert r["extraction"]["report_cmp"]["status"] == "AMBIGUOUS"
    assert r["action"] == "REVIEW_REQUIRED"
    assert any(w.startswith("AMBIGUOUS_REPORT_CMP") for w in r["warnings"])


# ---------------------------------------------------------------- complete-match policy for ATTACH_SOURCE

def icici_call(cmp_line="CMP: INR 720 Target Price: INR 920 28%", extra=()):
    """ICICI layout with a free-form price line and optional extra lines (synthetic)."""
    return make_pdf([
        ["Please refer to important disclosures at the end of this report", "BUY (Maintain)",
         f"{cmp_line} ICICI Securities Limited is the author and distributor of this report",
         "31 August 2026 India | Equity Research | Company Update", "HDFC Bank", "Banking",
         "Ravi Sample ravi.sample@icicisecurities.com", *extra],
        ["ICICI Securities Limited SEBI Registration INZ000183631"],
    ])


def test_complete_match_attaches_source(intake_env):
    add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=720, tp=920,
            entry=715, stop=680, horizon="3 months")
    r = preview(intake_env, icici_call(extra=("Entry range: INR 715", "Stop loss: INR 680", "Investment horizon: 3 months")))
    assert r["action"] == "ATTACH_SOURCE" and r["differences"] == [] and r["not_stated_in_report"] == []


def test_missing_target_cannot_attach(intake_env):
    add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=720, tp=920)
    r = preview(intake_env, icici_call(cmp_line="CMP: INR 720"))
    assert r["extraction"]["target"]["status"] == "UNKNOWN"
    assert r["action"] == "REVIEW_REQUIRED"
    assert "MISSING_MANDATORY_FIELD: target is not stated in this report" in r["warnings"]


def test_missing_cmp_and_target_cannot_attach(intake_env):
    add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=720, tp=920)
    r = preview(intake_env, icici_call(cmp_line="Rating unchanged"))
    assert r["action"] == "REVIEW_REQUIRED"
    assert {w for w in r["warnings"] if w.startswith("MISSING_MANDATORY_FIELD")} == {
        "MISSING_MANDATORY_FIELD: report_cmp is not stated in this report",
        "MISSING_MANDATORY_FIELD: target is not stated in this report"}


def test_missing_mandatory_fields_on_both_sides_still_cannot_attach(intake_env):
    add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=None, tp=None)
    r = preview(intake_env, icici_call(cmp_line="Rating unchanged"))
    assert r["action"] == "REVIEW_REQUIRED"


def test_stored_entry_absent_from_pdf_needs_review(intake_env):
    add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=720, tp=920, entry=725)
    r = preview(intake_env, icici_call())
    assert r["action"] == "REVIEW_REQUIRED"
    assert any(w.startswith("UNSTATED_STORED_FIELD: entry_low stored as 725") for w in r["warnings"])
    assert r["proposed_recommendation"] is None  # nothing is filled in


def test_stored_stop_and_horizon_absent_from_pdf_need_review(intake_env):
    add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=720, tp=920, stop=680, horizon="3 months")
    r = preview(intake_env, icici_call())
    assert r["action"] == "REVIEW_REQUIRED"
    unstated = [w for w in r["warnings"] if w.startswith("UNSTATED_STORED_FIELD")]
    assert any("stop_loss" in w for w in unstated) and any("time_horizon" in w for w in unstated)


def test_ambiguous_horizon_needs_review(intake_env):
    add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=720, tp=920)
    r = preview(intake_env, icici_call(extra=("Investment horizon: 3 months", "Holding horizon: 12 months")))
    assert r["extraction"]["time_horizon"]["status"] == "AMBIGUOUS"
    assert r["action"] == "REVIEW_REQUIRED"
    assert "AMBIGUOUS_OPTIONAL_FIELD: time_horizon" in r["warnings"]


def test_ambiguous_entry_high_needs_review(intake_env, monkeypatch):
    from app.services import broker_pdf_intake_service as intake
    from app.services.broker_pdf_extraction import AMBIGUOUS, Field
    real = intake.extract_fields_isolated

    def only_entry_high_ambiguous(content):
        ex = real(content)
        ex.entry_low, ex.entry_high = Field(715, "KNOWN"), Field(None, AMBIGUOUS)
        return ex

    monkeypatch.setattr(intake, "extract_fields_isolated", only_entry_high_ambiguous)
    add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=720, tp=920, entry=715)
    r = preview(intake_env, icici_call())
    assert r["action"] == "REVIEW_REQUIRED"
    assert "AMBIGUOUS_OPTIONAL_FIELD: entry_high" in r["warnings"]


def test_ambiguous_entry_range_from_report_needs_review(intake_env):
    ex = extract_fields(icici_call(extra=("Entry range: INR 715 - INR 720", "Entry range: INR 715 - INR 725")))
    assert ex.entry_high.status == "AMBIGUOUS"
    add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=720, tp=920)
    r = preview(intake_env, icici_call(extra=("Entry range: INR 715 - INR 720", "Entry range: INR 715 - INR 725")))
    assert r["action"] == "REVIEW_REQUIRED"


@pytest.mark.parametrize("stored,field", [
    ({"cmp": 720, "tp": 950}, "target"),
    ({"cmp": 700, "tp": 920}, "report_cmp (recommended_price)"),
    ({"cmp": 720, "tp": 920, "stop": 650}, "stop_loss"),
    ({"cmp": 720, "tp": 920, "horizon": "12 months"}, "time_horizon"),
])
def test_conflicting_mandatory_or_optional_value_is_conflict(intake_env, stored, field):
    add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", **stored)
    r = preview(intake_env, icici_call(extra=("Stop loss: INR 680", "Investment horizon: 3 months")))
    assert r["action"] == "CONFLICT_REVIEW_REQUIRED"
    assert field in {d["field"] for d in r["differences"]}


# ---------------------------------------------------------------- input safety

@pytest.mark.parametrize("name,content,detail", [
    ("notes.txt", b"hello", "Only .pdf files are supported"),
    ("fake.pdf", b"not really a pdf", "File content is not a valid PDF"),
    ("empty.pdf", b"", "File is empty"),
])
def test_invalid_input_is_rejected(client, intake_env, name, content, detail):
    resp = client.post("/api/broker-uploads/preview", files={"file": (name, content, "application/pdf")})
    assert resp.status_code == 400 and resp.json()["detail"] == detail


def test_corrupt_pdf_body_is_rejected_not_a_server_error(client, intake_env):
    resp = client.post("/api/broker-uploads/preview", files={"file": ("x.pdf", b"%PDF-1.4\n" + b"0" * 2000, "application/pdf")})
    assert resp.status_code == 400 and "could not be read as a PDF" in resp.json()["detail"]


def test_size_limit_and_filename_containment(client, intake_env, monkeypatch):
    monkeypatch.setattr(uploads, "MAX_FILE_SIZE_BYTES", 1000)
    resp = client.post("/api/broker-uploads/preview", files={"file": ("big.pdf", b"%PDF-" + b"0" * 2000, "application/pdf")})
    assert resp.status_code == 400 and "too large" in resp.json()["detail"]
    monkeypatch.setattr(uploads, "MAX_FILE_SIZE_BYTES", 25 * 1024 * 1024)
    r = preview(intake_env, motilal(), name="../../etc/evil report.pdf")
    assert r["file"]["safe_filename"] == "evil_report.pdf"


def test_invalid_discovery_url_is_rejected(intake_env):
    with pytest.raises(uploads.BrokerUploadError):
        preview(intake_env, motilal(), discovery_source="Trendlyne", discovery_url="javascript:alert(1)")
    ok = preview(intake_env, motilal(), discovery_source="Trendlyne", discovery_url="https://trendlyne.com/research-reports/x/")
    assert ok["discovery"]["discovery_url_status"] == "PROVIDED"


# ---------------------------------------------------------------- manifest compatibility and non-persistence

def test_legacy_manifest_entries_stay_valid_and_are_duplicate_checked(client, intake_env):
    content = icici(company="InterGlobe Aviation", cmp="5,234", tp="6,020", prev=None)
    folder = uploads.UPLOAD_DIR / "icici_securities"
    folder.mkdir(parents=True)
    (folder / "legacy.pdf").write_bytes(content)
    legacy = {"upload_id": "20260903_203319_1efbd821", "broker_name": "ICICI Securities", "stock_symbol": "INDIGO",
              "note": None, "original_filename": "legacy.pdf",
              "stored_path": "uploads/icici_securities/legacy.pdf", "size_bytes": len(content),
              "uploaded_at": "2026-09-03T20:33:19+00:00"}
    uploads.MANIFEST_PATH.write_text(json.dumps([legacy]), encoding="utf-8")

    listed = client.get("/api/broker-uploads").json()
    assert listed[0]["upload_id"] == legacy["upload_id"] and listed[0]["sha256"] is None
    r = preview(intake_env, content)
    assert r["file"]["duplicate_of_upload_id"] == legacy["upload_id"]
    resp = client.post("/api/broker-uploads", data={"broker_name": "ICICI Securities"},
                       files={"file": ("again.pdf", content, "application/pdf")})
    assert resp.status_code == 409 and "DUPLICATE_FILE" in resp.json()["detail"]
    assert json.loads(uploads.MANIFEST_PATH.read_text(encoding="utf-8")) == [legacy]  # not rewritten


def test_new_uploads_record_sha_and_discovery(client, intake_env):
    content = motilal()
    resp = client.post("/api/broker-uploads", data={"broker_name": "Motilal Oswal", "discovery_source": "Trendlyne"},
                       files={"file": ("r.pdf", content, "application/pdf")})
    body = resp.json()
    assert resp.status_code == 200
    assert body["sha256"] == hashlib.sha256(content).hexdigest()
    assert (body["discovery_source"], body["discovery_url"]) == ("Trendlyne", None)


def test_preview_endpoint_persists_nothing(client, intake_env):
    tables = [BrokerRecommendation, SourceReference, RecommendationSource, StockMaster, BrokerMaster]
    counts = [intake_env.query(t).count() for t in tables]
    resp = client.post("/api/broker-uploads/preview", data={"discovery_source": "Trendlyne"},
                       files={"file": ("adanient.pdf", motilal(), "application/pdf")})
    assert resp.status_code == 200 and resp.json()["action"] == "NEW" and resp.json()["persisted"] is False
    assert [intake_env.query(t).count() for t in tables] == counts
    assert not uploads.UPLOAD_DIR.exists()  # no file, no manifest


# ---------------------------------------------------------------- same-day ambiguity

def test_single_same_day_match_is_selected(intake_env):
    rec = add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=720, tp=920)
    r = preview(intake_env, icici())
    assert r["action"] == "ATTACH_SOURCE" and r["existing_match"]["recommendation_id"] == rec.recommendation_id
    assert r["candidate_recommendation_ids"] == []


def test_multiple_same_day_matches_are_never_picked_silently(intake_env):
    a = add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=720, tp=920)
    b = add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=720, tp=920, status="SUPERSEDED")
    r = preview(intake_env, icici())
    assert r["action"] == "REVIEW_REQUIRED" and r["existing_match"] is None
    ids = sorted([a.recommendation_id, b.recommendation_id])
    assert r["candidate_recommendation_ids"] == ids
    assert f"MULTIPLE_SAME_DAY_MATCHES: recommendations {ids[0]}, {ids[1]}" in r["warnings"]


def test_same_day_different_rating_does_not_block_the_single_rating_match(intake_env):
    intake_env.add(RatingNormalization(original_rating="Sell", normalized_rating="SELL"))
    intake_env.commit()
    add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=720, tp=500, rating="SELL")
    buy = add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=720, tp=920)
    r = preview(intake_env, icici())
    assert r["action"] == "ATTACH_SOURCE" and r["existing_match"]["recommendation_id"] == buy.recommendation_id


def test_same_day_only_different_rating_is_a_conflict(intake_env):
    add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=720, tp=920, rating="SELL")
    r = preview(intake_env, icici())
    assert r["action"] == "CONFLICT_REVIEW_REQUIRED"
    assert r["differences"] == [{"field": "normalized_rating", "report": "BUY", "stored": "SELL"}]


# ---------------------------------------------------------------- PDF linked to several recommendations

def _sha(content):
    return hashlib.sha256(content).hexdigest()


def test_pdf_linked_only_to_the_selected_recommendation_is_exact_duplicate(intake_env):
    content = icici()
    rec = add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=720, tp=920, sha=_sha(content))
    r = preview(intake_env, content)
    assert r["action"] == "EXACT_DUPLICATE" and r["document_linked_recommendation_ids"] == [rec.recommendation_id]
    assert not any(w.startswith("DOCUMENT_ALREADY_LINKED") for w in r["warnings"])


def test_pdf_linked_to_selected_and_another_recommendation_needs_review(intake_env):
    content = icici()
    other = add_rec(intake_env, "ADANIENT", "Motilal Oswal", "2026-08-01", cmp=3000, tp=3500, sha=_sha(content))
    rec = add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=720, tp=920, sha=_sha(content))
    r = preview(intake_env, content)
    assert r["action"] == "REVIEW_REQUIRED"
    assert r["document_linked_recommendation_ids"] == sorted([other.recommendation_id, rec.recommendation_id])
    assert f"DOCUMENT_ALREADY_LINKED: this exact PDF is already evidence for recommendation(s) {other.recommendation_id}" in r["warnings"]


def test_linked_elsewhere_warning_is_kept_alongside_an_economic_conflict(intake_env):
    content = icici()
    others = [add_rec(intake_env, "ADANIENT", "Motilal Oswal", day, cmp=3000, tp=3500, sha=_sha(content))
              for day in ("2026-08-01", "2026-07-01")]
    add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=720, tp=999)  # target differs
    r = preview(intake_env, content)
    assert r["action"] == "CONFLICT_REVIEW_REQUIRED"
    ids = sorted(o.recommendation_id for o in others)
    assert r["document_linked_recommendation_ids"] == ids
    assert f"DOCUMENT_ALREADY_LINKED: this exact PDF is already evidence for recommendation(s) {ids[0]}, {ids[1]}" in r["warnings"]


def test_linked_elsewhere_with_multiple_same_day_matches_still_warns(intake_env):
    content = icici()
    other = add_rec(intake_env, "ADANIENT", "Motilal Oswal", "2026-08-01", cmp=3000, tp=3500, sha=_sha(content))
    add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=720, tp=920)
    add_rec(intake_env, "HDFCBANK", "ICICI Securities", "2026-08-31", cmp=720, tp=920)
    before = intake_env.query(RecommendationSource).count(), intake_env.query(SourceReference).count()
    r = preview(intake_env, content)
    assert r["action"] == "REVIEW_REQUIRED"
    assert any(w.startswith("MULTIPLE_SAME_DAY_MATCHES") for w in r["warnings"])
    assert any(w.startswith("DOCUMENT_ALREADY_LINKED") and str(other.recommendation_id) in w for w in r["warnings"])
    assert (intake_env.query(RecommendationSource).count(), intake_env.query(SourceReference).count()) == before
