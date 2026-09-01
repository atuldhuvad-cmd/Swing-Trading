"""Personal trade workflow validation on disposable DB copy. Does not touch production."""
from __future__ import annotations

import json
import math
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(r"D:\Swing Trading")
PROD = ROOT / "data" / "swing_trading.db"
COPY = ROOT / "scratch" / "personal_workflow_validation.db"
sys.path.insert(0, str(ROOT / "backend"))

os.environ["DATABASE_URL"] = f"sqlite:///{COPY.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.database import SessionLocal, get_db  # noqa: E402

defects: list[str] = []
notes: list[str] = []


def record_counts(path: Path) -> dict:
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    out = {
        "ohlcv": c.execute("SELECT COUNT(*) FROM daily_ohlcv").fetchone()[0],
        "fundamental_snapshot": c.execute("SELECT COUNT(*) FROM fundamental_snapshot").fetchone()[0],
        "fundamental_metric": c.execute("SELECT COUNT(*) FROM fundamental_metric").fetchone()[0],
        "candidate_evaluation_run": c.execute("SELECT COUNT(*) FROM candidate_evaluation_run").fetchone()[0],
        "candidate_criterion_result": c.execute("SELECT COUNT(*) FROM candidate_criterion_result").fetchone()[0],
        "risk_reward_result": c.execute("SELECT COUNT(*) FROM risk_reward_result").fetchone()[0],
        "broker_recommendation": c.execute("SELECT COUNT(*) FROM broker_recommendation").fetchone()[0],
        "trade_journal": c.execute("SELECT COUNT(*) FROM trade_journal").fetchone()[0],
        "integrity": c.execute("PRAGMA integrity_check").fetchone()[0],
        "fk": c.execute("PRAGMA foreign_key_check").fetchall(),
    }
    c.close()
    return out


def client_for_copy():
    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def main() -> int:
    if not PROD.exists():
        defects.append("production DB missing")
        return 1

    before_prod = record_counts(PROD)
    shutil.copy2(PROD, COPY)
    before_copy = record_counts(COPY)
    trade_count_before_copy = before_copy["trade_journal"]

    client = client_for_copy()

    # Route prefix check (frontend expects /api/trades via vite proxy)
    for path in ["/trades/", "/api/trades/"]:
        r = client.get(path)
        notes.append(f"GET {path} -> {r.status_code}")

    api_prefix = "/api/trades" if client.get("/api/trades/").status_code == 200 else "/trades"
    if api_prefix != "/api/trades":
        defects.append("Trades router not mounted at /api/trades; frontend tradesApi uses /api baseURL")

    def post(path, payload):
        return client.post(api_prefix + path, json=payload)

    def patch(trade_id, payload):
        return client.patch(f"{api_prefix}/{trade_id}", json=payload)

    def get(path):
        return client.get(api_prefix + path)

    # Position sizing deterministic cases
    cases = [
        ({"entry_price": 100, "stop_price": 90, "max_risk_amount": 500}, 50, 10.0, 5000.0),
        ({"entry_price": 100, "stop_price": 90, "max_risk_amount": 500, "max_capital_allocation": 2000}, 20, 10.0, 2000.0),
    ]
    for payload, exp_qty, exp_risk, exp_cap in cases:
        r = post("/position-size", payload)
        if r.status_code != 200:
            defects.append(f"position-size failed {payload}: {r.status_code} {r.text}")
            continue
        d = r.json()
        if d.get("status") != "CALCULATED" or d.get("quantity") != exp_qty:
            defects.append(f"position-size qty expected {exp_qty} got {d}")
        if float(d.get("per_share_risk", -1)) != exp_risk:
            defects.append(f"per_share_risk expected {exp_risk}")
        if float(d.get("total_capital", -1)) != exp_cap:
            defects.append(f"total_capital expected {exp_cap}")

    r = post("/position-size", {"entry_price": 90, "stop_price": 100, "max_risk_amount": 500})
    if r.json().get("status") != "NOT_CALCULATED":
        defects.append("invalid LONG prices should NOT_CALCULATE")

    r = post("/position-size", {"entry_price": 100, "max_risk_amount": 500})
    if r.status_code != 422:
        defects.append("missing stop_price should 422")

    # Use CIPLA (stock_id 19, eval 34, has RR)
    ev = client.get("/api/evidence/stocks/19")
    if ev.status_code != 200:
        defects.append(f"evidence CIPLA failed {ev.status_code}")
        return 1
    ev_body = ev.json()
    eval_id = ev_body["candidate"]["evaluation_id"]
    rr = ev_body.get("risk_reward") or {}
    rr_keys = set(rr.keys())
    if "result_id" not in rr_keys:
        defects.append("Evidence risk_reward missing result_id for trade linkage")
    if "entry_reference" not in rr_keys and "entry" in rr_keys:
        notes.append("Evidence RR uses entry/stop not entry_reference/stop_loss (TradePlanForm mismatch)")

    # Resolve RR result_id from DB
    c = sqlite3.connect(COPY)
    rr_row = c.execute(
        "SELECT result_id FROM risk_reward_result WHERE evaluation_id=? ORDER BY result_id DESC LIMIT 1",
        (eval_id,),
    ).fetchone()
    c.close()
    rr_id = rr_row[0] if rr_row else None

    planned = {
        "stock_id": 19,
        "candidate_evaluation_id": eval_id,
        "risk_reward_result_id": rr_id,
        "status": "PLANNED",
        "side": "LONG",
        "planned_entry_price": 1458.8,
        "planned_stop_price": 1421.105,
        "planned_target_price": 1476.288,
        "quantity": 10,
        "trade_notes": "PERSONAL_WORKFLOW_VALIDATION_TEST",
    }
    r = post("/", planned)
    if r.status_code != 200:
        defects.append(f"create PLANNED failed: {r.status_code} {r.text}")
        return 1
    trade = r.json()
    if trade["status"] != "PLANNED":
        defects.append("created trade not PLANNED")
    if trade.get("entry_price") is not None:
        defects.append("PLANNED trade must not have entry_price at create")
    if trade.get("candidate_evaluation_id") != eval_id:
        defects.append("candidate_evaluation_id not pinned")
    if trade.get("risk_reward_result_id") != rr_id:
        defects.append("risk_reward_result_id not pinned")
    trade_id = trade["trade_id"]

    # Cross-stock linkage rejected
    r = post("/", {**planned, "stock_id": 20})
    if r.status_code != 422:
        defects.append("cross-stock candidate linkage should 422")

    # OPEN requires explicit fields
    r = patch(trade_id, {"status": "OPEN"})
    if r.status_code != 422:
        defects.append("OPEN without fields should 422")

    r = patch(trade_id, {
        "status": "OPEN",
        "quantity": 10,
        "entry_price": 1460.25,
        "entry_date": "2026-08-20T10:30:00Z",
        "entry_price_source": "TEST manual observation",
        "entry_note": "Workflow validation test entry note",
    })
    if r.status_code != 200:
        defects.append(f"OPEN failed: {r.status_code} {r.text}")
    else:
        opened = r.json()
        if float(opened["entry_price"]) != 1460.25:
            defects.append("entry_price not manual value")
        if opened.get("entry_price_source") != "TEST manual observation":
            defects.append("entry_price_source missing")
        if opened.get("entry_note") != "Workflow validation test entry note":
            defects.append("entry_note missing")
        if opened.get("entry_price_source") == opened.get("entry_note"):
            defects.append("entry source conflated with note")

    # CLOSE
    r = patch(trade_id, {"status": "CLOSED", "exit_price": 1475.0, "exit_date": "2026-08-21T15:00:00Z", "exit_price_source": "TEST manual exit observation", "exit_note": "exit note"})
    if r.status_code != 200:
        defects.append(f"CLOSE failed: {r.status_code} {r.text}")
    else:
        closed = r.json()
        gross = (1475.0 - 1460.25) * 10
        if abs(float(closed["gross_pnl"]) - gross) > 0.01:
            defects.append(f"gross_pnl expected {gross} got {closed['gross_pnl']}")
        if closed.get("net_pnl") is not None:
            defects.append("net_pnl should be null without manual_charges")

    r = patch(trade_id, {"status": "OPEN"})
    if r.status_code != 422 or "Invalid transition" not in r.text:
        defects.append("CLOSED -> OPEN should reject")

    # CANCELLED path on separate trade
    r = post("/", {"stock_id": 19, "status": "PLANNED", "side": "LONG", "trade_notes": "CANCEL_TEST"})
    cancel_id = r.json()["trade_id"]
    r = patch(cancel_id, {"status": "CANCELLED"})
    if r.status_code != 200:
        defects.append(f"CANCEL failed {r.status_code}")
    r = patch(cancel_id, {"status": "OPEN", "quantity": 1, "entry_price": 1, "entry_date": "2026-08-20T10:00:00Z", "entry_price_source": "x"})
    if r.status_code != 422:
        defects.append("CANCELLED -> OPEN should reject")

    # Historical pin: newer eval must not rewrite trade
    pinned_eval = trade["candidate_evaluation_id"]
    got = get(f"/{trade_id}").json()
    if got["candidate_evaluation_id"] != pinned_eval:
        defects.append("trade evaluation reference changed on read")

    # Cleanup test rows from disposable copy only
    c = sqlite3.connect(COPY)
    c.execute("DELETE FROM trade_journal WHERE trade_notes LIKE '%PERSONAL_WORKFLOW_VALIDATION_TEST%' OR trade_notes='CANCEL_TEST'")
    c.commit()
    after_copy = record_counts(COPY)
    c.close()

    after_prod = record_counts(PROD)

    print("BEFORE_PROD", json.dumps(before_prod))
    print("AFTER_PROD", json.dumps(after_prod))
    print("COPY_TRADES_BEFORE", trade_count_before_copy)
    print("COPY_TRADES_AFTER_CLEANUP", after_copy["trade_journal"])
    print("NOTES", notes)
    print("DEFECTS", defects)

    if before_prod != after_prod:
        defects.append("PRODUCTION COUNTS CHANGED")
    if after_copy["trade_journal"] != trade_count_before_copy:
        defects.append("Disposable copy trade count not restored")

    app.dependency_overrides.clear()
    return 1 if defects else 0


if __name__ == "__main__":
    raise SystemExit(main())
