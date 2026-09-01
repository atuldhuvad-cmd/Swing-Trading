import json
from decimal import Decimal
from app.models import CandidateEvaluationRun, CandidateCriterionResult
from app.services.candidate_service import CandidateService
from app.services.candidate_config import LEGACY_BATCH_A_POST_IMPORT_CONFIG, PHASE5_TREND_SCREEN_V1
from app.services.risk_reward_service import RiskRewardService
from app.models import StockMaster

LEGACY_FINGERPRINT = "9ac50fd3f34e2242b2a635eb8a84c66d0316f757caaa20944d59d185d7b64a18"

COMPLETE_TECH = {
    "SMA20": 100.0,
    "SMA50": 110.0,
    "SMA200": 90.0,
    "ATR14": 5.0,
    "latest_close": 120.0,
    "sessions": 247,
    "RSI14": 55.0,
    "MACD": 1.0,
    "MACD_signal": 2.0,
    "ROC20": 1.0,
    "Liquidity20": 1.0,
    "Breakout20_status": "NEGATIVE",
}
COMPLETE_FUND = {"revenue": {"value": 1000, "status": "KNOWN"}}


def _stock(db, symbol):
    stock = StockMaster(nse_symbol=symbol, company_name=symbol)
    db.add(stock)
    db.commit()
    return stock


def _eval(db, stock, tech=None, fund=None, config=None):
    return CandidateService.evaluate_candidate(
        db,
        stock.stock_id,
        config if config is not None else PHASE5_TREND_SCREEN_V1,
        tech if tech is not None else dict(COMPLETE_TECH),
        fund if fund is not None else dict(COMPLETE_FUND),
    )


def test_phase5_config_matches_approved_policy():
    print("PROPOSED_PHASE5_CONFIG", json.dumps(PHASE5_TREND_SCREEN_V1, sort_keys=True, indent=2))
    ids = [c["id"] for c in PHASE5_TREND_SCREEN_V1["criteria"]]
    assert PHASE5_TREND_SCREEN_V1["name"] == "phase5_trend_screen_v1"
    assert "close_gt_sma50" in ids
    assert "sma50_gt_sma200" in ids
    close_rule = next(c for c in PHASE5_TREND_SCREEN_V1["criteria"] if c["id"] == "close_gt_sma50")
    trend_rule = next(c for c in PHASE5_TREND_SCREEN_V1["criteria"] if c["id"] == "sma50_gt_sma200")
    assert close_rule["field"] == "latest_close"
    assert close_rule["compare_to"] == "SMA50"
    assert close_rule["operator"] == ">"
    assert close_rule["mandatory"] is True
    assert trend_rule["field"] == "SMA50"
    assert trend_rule["compare_to"] == "SMA200"
    assert trend_rule["mandatory"] is False
    assert not any(c.get("field") == "RSI14" or c["id"] == "RSI14" for c in PHASE5_TREND_SCREEN_V1["criteria"])
    assert not any("Breakout" in c["id"] or c.get("field") == "MACD" or "ROC" in c["id"] for c in PHASE5_TREND_SCREEN_V1["criteria"])
    assert not any("rr" in c["id"].lower() for c in PHASE5_TREND_SCREEN_V1["criteria"])
    legacy_fp = CandidateService.get_config_fingerprint(LEGACY_BATCH_A_POST_IMPORT_CONFIG)
    phase5_fp = CandidateService.get_config_fingerprint(PHASE5_TREND_SCREEN_V1)
    assert legacy_fp == LEGACY_FINGERPRINT
    assert phase5_fp != legacy_fp
    assert phase5_fp == "146408d7d5de3ce55acd5465d2c788acca9d8e1875c21e1af470151a3f0f97fe"
    from app.services.candidate_config import ACTIVE_CANDIDATE_CONFIG
    assert ACTIVE_CANDIDATE_CONFIG is PHASE5_TREND_SCREEN_V1
    assert CandidateService.get_active_config()["name"] == "phase5_trend_screen_v1"


def test_missing_sma50_insufficient(db_session):
    stock = _stock(db_session, "P5_NO_SMA50")
    tech = dict(COMPLETE_TECH)
    del tech["SMA50"]
    run = _eval(db_session, stock, tech=tech)
    assert run.classification == "INSUFFICIENT_DATA"


def test_missing_sma200_insufficient(db_session):
    stock = _stock(db_session, "P5_NO_SMA200")
    tech = dict(COMPLETE_TECH)
    del tech["SMA200"]
    run = _eval(db_session, stock, tech=tech)
    assert run.classification == "INSUFFICIENT_DATA"


def test_missing_revenue_insufficient(db_session):
    stock = _stock(db_session, "P5_NO_REV")
    run = _eval(db_session, stock, fund={})
    assert run.classification == "INSUFFICIENT_DATA"


def test_unknown_revenue_insufficient(db_session):
    stock = _stock(db_session, "P5_UNK_REV")
    run = _eval(db_session, stock, fund={"revenue": {"value": None, "status": "UNKNOWN"}})
    assert run.classification == "INSUFFICIENT_DATA"


def test_revenue_non_positive_rejected(db_session):
    stock = _stock(db_session, "P5_REV0")
    run = _eval(db_session, stock, fund={"revenue": {"value": 0, "status": "KNOWN"}})
    assert run.classification == "REJECTED"


def test_close_not_above_sma50_rejected(db_session):
    stock = _stock(db_session, "P5_BELOW")
    tech = dict(COMPLETE_TECH)
    tech["latest_close"] = 110.0
    tech["SMA50"] = 110.0
    run = _eval(db_session, stock, tech=tech)
    assert run.classification == "REJECTED"


def test_close_above_sma50_but_sma50_not_above_sma200_watch(db_session):
    stock = _stock(db_session, "P5_WATCH")
    tech = dict(COMPLETE_TECH)
    tech["latest_close"] = 120.0
    tech["SMA50"] = 100.0
    tech["SMA200"] = 110.0
    run = _eval(db_session, stock, tech=tech)
    assert run.classification == "WATCH"


def test_close_above_sma50_and_sma50_above_sma200_final(db_session):
    stock = _stock(db_session, "P5_FINAL")
    run = _eval(db_session, stock)
    assert run.classification == "FINAL_CANDIDATE"


def test_unknown_never_becomes_pass(db_session):
    stock = _stock(db_session, "P5_UNK_NEVER_PASS")
    tech = dict(COMPLETE_TECH)
    tech["ATR14"] = {"value": None, "status": "UNKNOWN"}
    run = _eval(db_session, stock, tech=tech)
    db_session.flush()
    assert run.classification == "INSUFFICIENT_DATA"
    rows = db_session.query(CandidateCriterionResult).filter_by(evaluation_id=run.evaluation_id).all()
    unknown_rows = [r for r in rows if r.state == "UNKNOWN"]
    assert unknown_rows
    atr = next(r for r in rows if r.criterion_identifier == "ATR14_known")
    assert atr.state == "UNKNOWN"
    assert all(r.state != "PASS" for r in unknown_rows)
    assert run.classification != "FINAL_CANDIDATE"


def test_old_history_and_config_preserved(db_session):
    stock = _stock(db_session, "P5_HISTORY")
    old = CandidateService.evaluate_candidate(
        db_session,
        stock.stock_id,
        LEGACY_BATCH_A_POST_IMPORT_CONFIG,
        {k: COMPLETE_TECH[k] for k in ["SMA20", "SMA50", "SMA200", "RSI14", "MACD", "ATR14", "ROC20", "Liquidity20"]},
        COMPLETE_FUND,
    )
    db_session.flush()
    old_id = old.evaluation_id
    old_class = old.classification
    old_fp = old.config_fingerprint
    old_snap = old.config_snapshot
    new = _eval(db_session, stock)
    db_session.flush()
    preserved = db_session.get(CandidateEvaluationRun, old_id)
    assert preserved.classification == old_class
    assert preserved.config_fingerprint == old_fp == LEGACY_FINGERPRINT
    assert preserved.config_snapshot == old_snap
    assert new.config_fingerprint != old_fp
    assert new.evaluation_id != old_id
    assert json.loads(preserved.config_snapshot)["name"] == "batch_a_post_import_evidence_gate"
    assert json.loads(new.config_snapshot)["name"] == "phase5_trend_screen_v1"


def test_rr_does_not_affect_classification(db_session):
    stock = _stock(db_session, "P5_RR")
    run = _eval(db_session, stock)
    before = run.classification
    RiskRewardService.calculate_risk_reward(
        db_session,
        run.evaluation_id,
        {"atr_multiplier": 1.5, "buffer_percent": 0.01},
        {"ATR14": 5.0, "Support20": 80.0, "Resistance20": 150.0},
        120.0,
    )
    db_session.flush()
    again = db_session.get(CandidateEvaluationRun, run.evaluation_id)
    assert again.classification == before == "FINAL_CANDIDATE"
    tech_with_rr = dict(COMPLETE_TECH)
    tech_with_rr["risk_reward_ratio"] = Decimal("0.6052")
    stock2 = _stock(db_session, "P5_RR2")
    run2 = _eval(db_session, stock2, tech=tech_with_rr)
    assert run2.classification == "FINAL_CANDIDATE"
    ids = [c.criterion_identifier for c in db_session.query(CandidateCriterionResult).filter_by(evaluation_id=run2.evaluation_id)]
    assert "risk_reward_ratio" not in ids
