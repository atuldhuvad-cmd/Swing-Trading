"""INSURANCE entity semantics for the manual fundamental import.

Canonical line: the Policyholders' Account "Total Income" of the exchange-filed
life insurance results format (IRDAI Form A-RA TOTAL (A)). The bare label
"Total Income" used by BANK/NBFC is ambiguous for insurers and must be rejected.
"""
from datetime import date
from decimal import Decimal

from app.models import DataImportBatch, FundamentalMetric, FundamentalSnapshot, StockMaster
from app.schemas.fundamental import FundamentalManualImport, FundamentalMetricIn
from app.services.fundamental_catalog import (
    CANONICAL_SOURCE_LINE, ENTITY_TYPES, INSURANCE_REVENUE_LINE,
)

INSURANCE_LINE = "Total Income (Policyholders' Account)"


def _insurer(db_session):
    if not db_session.query(StockMaster).filter_by(nse_symbol="HDFCLIFE").first():
        db_session.add(StockMaster(nse_symbol="HDFCLIFE", company_name="HDFC Life Insurance Company Ltd."))
        db_session.commit()


def _payload(**kwargs):
    base = dict(
        nse_symbol="HDFCLIFE",
        entity_type="INSURANCE",
        as_of_date=date(2026, 3, 31),
        financial_period="FY2025-26",
        period_type="ANNUAL",
        source_name="NSE-filed audited annual financial results (board meeting outcome)",
        source_reference="https://example.invalid/hdfclife-fy26",
        statement_scope="CONSOLIDATED",
        source_line_item=INSURANCE_LINE,
        original_unit="INR_CRORE",
        metrics=[FundamentalMetricIn(metric_name="revenue", metric_value="1234.56", status="KNOWN")],
    )
    base.update(kwargs)
    return FundamentalManualImport(**base)


def _preview(client, payload):
    return client.post("/api/fundamentals/preview", json=payload.model_dump(mode="json"))


def _confirm(client, payload):
    preview = _preview(client, payload).json()
    return client.post("/api/fundamentals/confirm", json={
        "payload_sha256": preview["payload_sha256"],
        "payload": payload.model_dump(mode="json"),
    })


def test_catalog_exposes_insurance_policy(client):
    body = client.get("/api/fundamentals/catalog").json()
    assert "INSURANCE" in body["entity_types"]
    assert body["canonical_source_line"]["INSURANCE"] == INSURANCE_LINE
    assert body["revenue_policy"]["insurance"]["source_line_item"] == INSURANCE_LINE
    assert body["revenue_unit"] == "INR_CRORE"
    assert body["revenue_policy"]["preferred_scope"] == "CONSOLIDATED"
    assert "Total Income" in body["revenue_policy"]["insurance"]["do_not_substitute"]
    assert "Revenue from Operations" in body["revenue_policy"]["insurance"]["do_not_substitute"]
    assert "IRDAI" in body["revenue_policy"]["insurance"]["authority"]
    assert INSURANCE_REVENUE_LINE == INSURANCE_LINE
    assert body["entity_metric_key"]["INSURANCE"] == "insurance"


def test_insurance_entity_accepted_with_canonical_line(client, db_session):
    _insurer(db_session)
    res = _preview(client, _payload())
    assert res.status_code == 200
    data = res.json()
    assert data["entity_type"] == "INSURANCE"
    assert data["source_line_item"] == INSURANCE_LINE
    assert data["statement_scope"] == "CONSOLIDATED"
    assert data["original_unit"] == "INR_CRORE"
    assert data["persisted"] is False
    rev = next(m for m in data["metrics"] if m["metric_name"] == "revenue")
    assert rev["status"] == "KNOWN" and rev["metric_value"] == "1234.56"


def test_revenue_from_operations_rejected_for_insurance(client, db_session):
    _insurer(db_session)
    res = _preview(client, _payload(source_line_item="Revenue from Operations"))
    assert res.status_code == 400
    assert INSURANCE_LINE in res.json()["detail"]


def test_bare_bank_total_income_rejected_for_insurance(client, db_session):
    """The BANK/NBFC mapping must not silently apply to insurers."""
    _insurer(db_session)
    res = _preview(client, _payload(source_line_item="Total Income"))
    assert res.status_code == 400
    assert INSURANCE_LINE in res.json()["detail"]
    assert CANONICAL_SOURCE_LINE["BANK"] == "Total Income"
    assert CANONICAL_SOURCE_LINE["INSURANCE"] != CANONICAL_SOURCE_LINE["BANK"]


def test_shareholders_account_line_rejected_for_insurance(client, db_session):
    _insurer(db_session)
    res = _preview(client, _payload(source_line_item="Total Income (Shareholders' Account)"))
    assert res.status_code == 400


def test_premium_lines_rejected_for_insurance(client, db_session):
    _insurer(db_session)
    for line in ("Gross premium income", "Net premium income", "Premium Income"):
        assert _preview(client, _payload(source_line_item=line)).status_code == 400


def test_missing_source_line_item_rejected_for_insurance(client, db_session):
    _insurer(db_session)
    res = _preview(client, _payload(source_line_item=None))
    assert res.status_code == 400
    assert "source_line_item is required" in res.json()["detail"]


def test_missing_and_wrong_unit_rejected_for_insurance(client, db_session):
    _insurer(db_session)
    missing = _preview(client, _payload(original_unit=None))
    assert missing.status_code == 400
    assert "original_unit is required" in missing.json()["detail"]

    wrong = _preview(client, _payload(original_unit="INR_BILLION"))
    assert wrong.status_code == 400
    assert "Invalid original_unit" in wrong.json()["detail"]


def test_consolidated_and_explicit_standalone_accepted(client, db_session):
    _insurer(db_session)
    consolidated = _confirm(client, _payload()).json()
    assert consolidated["persisted"] is True
    assert consolidated["statement_scope"] == "CONSOLIDATED"

    standalone = _confirm(client, _payload(
        financial_period="FY2024-25", statement_scope="STANDALONE")).json()
    assert standalone["persisted"] is True
    assert standalone["statement_scope"] == "STANDALONE"
    assert standalone["source_line_item"] == INSURANCE_LINE

    snap = db_session.query(FundamentalSnapshot).filter_by(
        snapshot_id=standalone["snapshot_id"]).one()
    assert snap.statement_scope == "STANDALONE"
    assert snap.entity_type == "INSURANCE"


def test_unknown_revenue_accepted_without_fabricated_value(client, db_session):
    _insurer(db_session)
    data = _preview(client, _payload(metrics=[])).json()
    rev = next(m for m in data["metrics"] if m["metric_name"] == "revenue")
    assert rev["status"] == "UNKNOWN"
    assert rev["metric_value"] is None
    assert rev["required_by_candidate_rule"] is True


def test_known_revenue_without_value_rejected(client, db_session):
    _insurer(db_session)
    res = _preview(client, _payload(
        metrics=[FundamentalMetricIn(metric_name="revenue", status="KNOWN")]))
    assert res.status_code == 400


def test_non_insurance_metrics_default_to_not_applicable(client, db_session):
    """No insurance-specific quality metric is introduced by this change."""
    _insurer(db_session)
    data = _preview(client, _payload()).json()
    statuses = {m["metric_name"]: m["status"] for m in data["metrics"]}
    for name in ("ebitda", "inventory_turnover", "nim", "gnpa", "capital_adequacy"):
        assert statuses[name] == "NOT_APPLICABLE"
    required = [m["metric_name"] for m in data["metrics"] if m["required_by_candidate_rule"]]
    assert required == ["revenue"]


def test_insurance_provenance_persisted_and_idempotent(client, db_session):
    _insurer(db_session)
    first = _confirm(client, _payload()).json()
    assert first["persisted"] is True and first["version"] == 1
    snap = db_session.query(FundamentalSnapshot).filter_by(snapshot_id=first["snapshot_id"]).one()
    assert snap.entity_type == "INSURANCE"
    assert snap.source_line_item == INSURANCE_LINE
    assert snap.statement_scope == "CONSOLIDATED"
    assert snap.original_unit == "INR_CRORE"
    assert snap.financial_period == "FY2025-26"
    assert snap.period_type == "ANNUAL"
    assert snap.as_of_date == date(2026, 3, 31)
    metric = db_session.query(FundamentalMetric).filter_by(
        snapshot_id=snap.snapshot_id, metric_name="revenue").one()
    assert metric.metric_value == Decimal("1234.56")

    replay = _confirm(client, _payload()).json()
    assert replay["status"] == "DUPLICATE"
    assert replay["persisted"] is False
    assert replay["audit_status"] == "SKIPPED_IDEMPOTENT"
    assert db_session.query(FundamentalSnapshot).filter_by(entity_type="INSURANCE").count() == 1
    batches = db_session.query(DataImportBatch).filter_by(import_type="FUNDAMENTAL_MANUAL").all()
    assert {b.status for b in batches} == {"COMPLETED", "SKIPPED_IDEMPOTENT"}


def test_insurance_revision_supersedes_and_preserves_history(client, db_session):
    _insurer(db_session)
    first = _confirm(client, _payload()).json()
    revised = _payload(metrics=[
        FundamentalMetricIn(metric_name="revenue", metric_value="2000.00", status="KNOWN")])
    assert _preview(client, revised).json()["action"] == "CONFLICT"
    second = _confirm(client, revised).json()
    assert second["version"] == 2 and second["superseded_previous"] is True
    old = db_session.query(FundamentalSnapshot).filter_by(snapshot_id=first["snapshot_id"]).one()
    assert old.is_superseded is True
    assert old.superseded_by_id == second["snapshot_id"]
    assert db_session.query(FundamentalMetric).filter_by(
        snapshot_id=old.snapshot_id, metric_name="revenue").one().metric_value == Decimal("1234.56")


def test_existing_entity_mappings_unchanged(client, db_session):
    """ORDINARY, BANK and NBFC behaviour must be untouched by the INSURANCE addition."""
    assert CANONICAL_SOURCE_LINE["ORDINARY"] == "Revenue from Operations"
    assert CANONICAL_SOURCE_LINE["BANK"] == "Total Income"
    assert CANONICAL_SOURCE_LINE["NBFC"] == "Total Income"
    assert set(ENTITY_TYPES) == {"ORDINARY", "BANK", "NBFC", "INSURANCE"}

    db_session.add(StockMaster(nse_symbol="CIPLA", company_name="Cipla Ltd."))
    db_session.add(StockMaster(nse_symbol="HDFCBANK", company_name="HDFC Bank Ltd."))
    db_session.add(StockMaster(nse_symbol="BAJFINANCE", company_name="Bajaj Finance Ltd."))
    db_session.commit()

    ordinary = _payload(nse_symbol="CIPLA", entity_type="ORDINARY",
                        source_line_item="Revenue from Operations")
    assert _preview(client, ordinary).status_code == 200
    bank = _payload(nse_symbol="HDFCBANK", entity_type="BANK", source_line_item="Total Income")
    assert _preview(client, bank).status_code == 200
    nbfc = _payload(nse_symbol="BAJFINANCE", entity_type="NBFC", source_line_item="Total Income")
    assert _preview(client, nbfc).status_code == 200

    # The insurance line must not be accepted for the pre-existing entity types.
    for payload in (ordinary, bank, nbfc):
        bad = _payload(nse_symbol=payload.nse_symbol, entity_type=payload.entity_type,
                       source_line_item=INSURANCE_LINE)
        assert _preview(client, bad).status_code == 400


def test_existing_entities_still_allow_defaulted_provenance(client, db_session):
    """Strict provenance applies only to INSURANCE; legacy leniency is preserved."""
    db_session.add(StockMaster(nse_symbol="GRASIM", company_name="Grasim Industries Ltd."))
    db_session.commit()
    lenient = _payload(nse_symbol="GRASIM", entity_type="ORDINARY",
                       source_line_item=None, original_unit=None)
    data = _preview(client, lenient).json()
    assert data["source_line_item"] == "Revenue from Operations"
    assert data["original_unit"] is None
