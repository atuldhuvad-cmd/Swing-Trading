from datetime import date
from decimal import Decimal
from app.models import FundamentalSnapshot, FundamentalMetric, StockMaster
from app.schemas.fundamental import FundamentalManualImport, FundamentalMetricIn, FundamentalConfirmRequest
from app.services.fundamental_import_service import FundamentalImportService
from app.services.fundamental_catalog import CANDIDATE_REQUIRED_METRICS


def _payload(**kwargs):
    base = dict(
        nse_symbol="RELIANCE",
        entity_type="ORDINARY",
        as_of_date=date(2026, 3, 31),
        financial_period="FY2026",
        period_type="ANNUAL",
        source_name="Company annual report",
        source_reference="https://example.invalid/report",
        statement_scope="CONSOLIDATED",
        source_line_item="Revenue from Operations",
        original_unit="INR_CRORE",
        metrics=[
            FundamentalMetricIn(metric_name="revenue", metric_value="1000.50", status="KNOWN"),
            FundamentalMetricIn(metric_name="ebitda", metric_value="200", status="KNOWN"),
        ],
    )
    base.update(kwargs)
    return FundamentalManualImport(**base)


def test_catalog_requires_revenue(client):
    res = client.get("/api/fundamentals/catalog")
    assert res.status_code == 200
    body = res.json()
    assert body["candidate_required_metrics"] == ["revenue"]
    assert CANDIDATE_REQUIRED_METRICS == ["revenue"]
    assert body["revenue_unit"] == "INR_CRORE"
    assert body["revenue_policy"]["ordinary"]["source_line_item"] == "Revenue from Operations"
    assert body["revenue_policy"]["bank"]["source_line_item"] == "Total Income"
    assert body["revenue_policy"]["nbfc"]["source_line_item"] == "Total Income"
    assert body["original_units"] == ["INR_CRORE", "INR_MILLION", "INR_LAKH"]
    assert body["canonical_source_line"]["ORDINARY"] == "Revenue from Operations"


def test_preview_does_not_persist(client, db_session):
    payload = _payload()
    res = client.post("/api/fundamentals/preview", json=payload.model_dump(mode="json"))
    assert res.status_code == 200
    data = res.json()
    assert data["persisted"] is False
    assert data["action"] == "ACCEPTED"
    assert data["statement_scope"] == "CONSOLIDATED"
    assert data["source_line_item"] == "Revenue from Operations"
    assert data["original_unit"] == "INR_CRORE"
    assert data["stock"]["nse_symbol"] == "RELIANCE"
    assert db_session.query(FundamentalSnapshot).count() == 0
    rev = next(m for m in data["metrics"] if m["metric_name"] == "revenue")
    assert rev["status"] == "KNOWN"
    assert rev["metric_value"] == "1000.50"
    nim = next(m for m in data["metrics"] if m["metric_name"] == "nim")
    assert nim["status"] == "NOT_APPLICABLE"


def test_ordinary_confirm_and_idempotent_replay(client, db_session):
    payload = _payload()
    preview = client.post("/api/fundamentals/preview", json=payload.model_dump(mode="json")).json()
    confirm = client.post("/api/fundamentals/confirm", json={
        "payload_sha256": preview["payload_sha256"],
        "payload": payload.model_dump(mode="json"),
    })
    assert confirm.status_code == 200
    body = confirm.json()
    assert body["persisted"] is True
    assert body["version"] == 1
    assert db_session.query(FundamentalSnapshot).count() == 1

    replay = client.post("/api/fundamentals/confirm", json={
        "payload_sha256": preview["payload_sha256"],
        "payload": payload.model_dump(mode="json"),
    }).json()
    assert replay["status"] == "DUPLICATE"
    assert replay["persisted"] is False
    assert replay["audit_status"] == "SKIPPED_IDEMPOTENT"
    assert db_session.query(FundamentalSnapshot).count() == 1
    from app.models import DataImportBatch
    batches = db_session.query(DataImportBatch).filter_by(import_type="FUNDAMENTAL_MANUAL").all()
    assert len(batches) == 2
    assert {b.status for b in batches} == {"COMPLETED", "SKIPPED_IDEMPOTENT"}
    snap = db_session.query(FundamentalSnapshot).one()
    assert snap.is_superseded is False
    assert snap.statement_scope == "CONSOLIDATED"
    assert snap.source_line_item == "Revenue from Operations"
    assert snap.original_unit == "INR_CRORE"


def test_revised_snapshot_preserves_history(client, db_session):
    payload = _payload()
    sha = client.post("/api/fundamentals/preview", json=payload.model_dump(mode="json")).json()["payload_sha256"]
    first = client.post("/api/fundamentals/confirm", json={"payload_sha256": sha, "payload": payload.model_dump(mode="json")}).json()

    revised = _payload(metrics=[
        FundamentalMetricIn(metric_name="revenue", metric_value="1100.00", status="KNOWN"),
        FundamentalMetricIn(metric_name="ebitda", metric_value="200", status="KNOWN"),
    ])
    preview = client.post("/api/fundamentals/preview", json=revised.model_dump(mode="json")).json()
    assert preview["action"] == "CONFLICT"
    second = client.post("/api/fundamentals/confirm", json={
        "payload_sha256": preview["payload_sha256"],
        "payload": revised.model_dump(mode="json"),
    }).json()
    assert second["persisted"] is True
    assert second["version"] == 2
    assert second["superseded_previous"] is True
    snaps = db_session.query(FundamentalSnapshot).order_by(FundamentalSnapshot.version).all()
    assert len(snaps) == 2
    assert snaps[0].is_superseded is True
    assert snaps[0].superseded_by_id == snaps[1].snapshot_id
    v1 = db_session.query(FundamentalMetric).filter_by(snapshot_id=snaps[0].snapshot_id, metric_name="revenue").one()
    v2 = db_session.query(FundamentalMetric).filter_by(snapshot_id=snaps[1].snapshot_id, metric_name="revenue").one()
    assert v1.metric_value == Decimal("1000.50")
    assert v2.metric_value == Decimal("1100.00")


def test_bank_and_nbfc_defaults(client, db_session):
    db_session.add(StockMaster(nse_symbol="AXISBANK", company_name="Axis Bank"))
    db_session.add(StockMaster(nse_symbol="BAJFINANCE", company_name="Bajaj Finance"))
    db_session.commit()

    bank = _payload(nse_symbol="AXISBANK", entity_type="BANK", source_line_item="Total Income", metrics=[
        FundamentalMetricIn(metric_name="revenue", status="UNKNOWN"),
        FundamentalMetricIn(metric_name="nim", metric_value="3.50", status="KNOWN"),
    ])
    bank_prev = client.post("/api/fundamentals/preview", json=bank.model_dump(mode="json")).json()
    inv = next(m for m in bank_prev["metrics"] if m["metric_name"] == "inventory_turnover")
    ebitda = next(m for m in bank_prev["metrics"] if m["metric_name"] == "ebitda")
    nim = next(m for m in bank_prev["metrics"] if m["metric_name"] == "nim")
    assert inv["status"] == "NOT_APPLICABLE"
    assert ebitda["status"] == "NOT_APPLICABLE"
    assert nim["status"] == "KNOWN"
    rev = next(m for m in bank_prev["metrics"] if m["metric_name"] == "revenue")
    assert rev["status"] == "UNKNOWN"

    nbfc = _payload(nse_symbol="BAJFINANCE", entity_type="NBFC", source_line_item="Total Income", metrics=[
        FundamentalMetricIn(metric_name="capital_adequacy", metric_value="15.5", status="KNOWN"),
    ])
    nbfc_prev = client.post("/api/fundamentals/preview", json=nbfc.model_dump(mode="json")).json()
    cad = next(m for m in nbfc_prev["metrics"] if m["metric_name"] == "capital_adequacy")
    ebitda_n = next(m for m in nbfc_prev["metrics"] if m["metric_name"] == "ebitda")
    assert cad["status"] == "KNOWN"
    assert ebitda_n["status"] == "NOT_APPLICABLE"
    rev_n = next(m for m in nbfc_prev["metrics"] if m["metric_name"] == "revenue")
    assert rev_n["status"] == "UNKNOWN"


def test_missing_evidence_stays_unknown(client):
    payload = _payload(metrics=[])
    data = client.post("/api/fundamentals/preview", json=payload.model_dump(mode="json")).json()
    rev = next(m for m in data["metrics"] if m["metric_name"] == "revenue")
    assert rev["status"] == "UNKNOWN"
    assert rev["metric_value"] is None
    assert rev["required_by_candidate_rule"] is True


def test_malformed_input(client):
    bad_symbol = _payload(nse_symbol="NOTASTOCK")
    assert client.post("/api/fundamentals/preview", json=bad_symbol.model_dump(mode="json")).status_code == 400

    bad_status = _payload(metrics=[FundamentalMetricIn(metric_name="revenue", metric_value="1", status="PASS")])
    assert client.post("/api/fundamentals/preview", json=bad_status.model_dump(mode="json")).status_code == 400

    known_missing = _payload(metrics=[FundamentalMetricIn(metric_name="revenue", status="KNOWN")])
    assert client.post("/api/fundamentals/preview", json=known_missing.model_dump(mode="json")).status_code == 400

    unknown_metric = _payload(metrics=[FundamentalMetricIn(metric_name="made_up", metric_value="1", status="KNOWN")])
    assert client.post("/api/fundamentals/preview", json=unknown_metric.model_dump(mode="json")).status_code == 400

    payload = _payload()
    preview = client.post("/api/fundamentals/preview", json=payload.model_dump(mode="json")).json()
    mismatch = client.post("/api/fundamentals/confirm", json={
        "payload_sha256": "0" * 64,
        "payload": payload.model_dump(mode="json"),
    })
    assert mismatch.status_code == 400
    assert client.post("/api/fundamentals/preview", json=payload.model_dump(mode="json")).json()["payload_sha256"] == preview["payload_sha256"]


def _confirm(client, payload):
    preview = client.post("/api/fundamentals/preview", json=payload.model_dump(mode="json")).json()
    return client.post("/api/fundamentals/confirm", json={
        "payload_sha256": preview["payload_sha256"],
        "payload": payload.model_dump(mode="json"),
    })


def test_provenance_units_and_standalone_persist(client, db_session):
    crore = _payload()
    body = _confirm(client, crore).json()
    snap = db_session.query(FundamentalSnapshot).filter_by(snapshot_id=body["snapshot_id"]).one()
    assert snap.original_unit == "INR_CRORE"
    assert snap.statement_scope == "CONSOLIDATED"
    rev = db_session.query(FundamentalMetric).filter_by(snapshot_id=snap.snapshot_id, metric_name="revenue").one()
    assert rev.metric_value == Decimal("1000.50")

    million = _payload(
        nse_symbol="RELIANCE",
        financial_period="FY2025",
        original_unit="INR_MILLION",
        metrics=[FundamentalMetricIn(metric_name="revenue", metric_value="1000.50", status="KNOWN")],
    )
    million_body = _confirm(client, million).json()
    m_snap = db_session.query(FundamentalSnapshot).filter_by(snapshot_id=million_body["snapshot_id"]).one()
    assert m_snap.original_unit == "INR_MILLION"
    m_rev = db_session.query(FundamentalMetric).filter_by(snapshot_id=m_snap.snapshot_id, metric_name="revenue").one()
    assert m_rev.metric_value == Decimal("1000.50")

    lakh = _payload(
        financial_period="FY2024",
        original_unit="INR_LAKH",
        metrics=[FundamentalMetricIn(metric_name="revenue", metric_value="1000.50", status="KNOWN")],
    )
    lakh_body = _confirm(client, lakh).json()
    l_snap = db_session.query(FundamentalSnapshot).filter_by(snapshot_id=lakh_body["snapshot_id"]).one()
    assert l_snap.original_unit == "INR_LAKH"

    standalone = _payload(
        financial_period="FY2023",
        statement_scope="STANDALONE",
        original_unit="INR_CRORE",
    )
    stand_body = _confirm(client, standalone).json()
    s_snap = db_session.query(FundamentalSnapshot).filter_by(snapshot_id=stand_body["snapshot_id"]).one()
    assert s_snap.statement_scope == "STANDALONE"
    assert s_snap.source_line_item == "Revenue from Operations"


def test_duplicate_detection_includes_provenance(client, db_session):
    payload = _payload()
    first = _confirm(client, payload).json()
    assert first["persisted"] is True

    different_unit = _payload(original_unit="INR_MILLION")
    preview = client.post("/api/fundamentals/preview", json=different_unit.model_dump(mode="json")).json()
    assert preview["action"] == "CONFLICT"
    second = _confirm(client, different_unit).json()
    assert second["persisted"] is True
    assert second["version"] == 2
    snaps = db_session.query(FundamentalSnapshot).order_by(FundamentalSnapshot.version).all()
    assert len(snaps) == 2
    assert snaps[0].is_superseded is True
    assert snaps[0].original_unit == "INR_CRORE"
    assert snaps[1].original_unit == "INR_MILLION"
    v1 = db_session.query(FundamentalMetric).filter_by(snapshot_id=snaps[0].snapshot_id, metric_name="revenue").one()
    v2 = db_session.query(FundamentalMetric).filter_by(snapshot_id=snaps[1].snapshot_id, metric_name="revenue").one()
    assert v1.metric_value == v2.metric_value == Decimal("1000.50")


def test_unknown_revenue_unchanged_with_provenance(client):
    payload = _payload(metrics=[], original_unit=None)
    data = client.post("/api/fundamentals/preview", json=payload.model_dump(mode="json")).json()
    rev = next(m for m in data["metrics"] if m["metric_name"] == "revenue")
    assert rev["status"] == "UNKNOWN"
    assert rev["metric_value"] is None
    assert data["original_unit"] is None
    assert data["statement_scope"] == "CONSOLIDATED"
