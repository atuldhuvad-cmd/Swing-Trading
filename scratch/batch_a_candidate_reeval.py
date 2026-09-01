"""Controlled Batch A candidate re-evaluation using existing application services.

Does not modify candidate rules, OHLCV, fundamentals, or historical evaluation rows.
Creates exactly one new evaluation per Batch A stock.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(r"D:\Swing Trading")
DB = ROOT / "data" / "swing_trading.db"
sys.path.insert(0, str(ROOT / "backend"))

from app.database import SessionLocal
from app.models import (
    StockMaster,
    DailyOhlcv,
    CandidateEvaluationRun,
    CandidateCriterionResult,
    RiskRewardResult,
)
from app.services.corporate_action_service import CorporateActionService
from app.services.technical_service import TechnicalService
from app.services.candidate_service import CandidateService
from app.services.fundamental_service import FundamentalService
from app.services.risk_reward_service import RiskRewardService

SYMBOLS = [
    "ADANIENT",
    "ADANIPORTS",
    "APOLLOHOSP",
    "ASIANPAINT",
    "AXISBANK",
    "BAJAJ-AUTO",
    "BAJAJFINSV",
    "BAJFINANCE",
    "BEL",
    "BHARTIARTL",
]
EXPECTED_SESSIONS = {
    "ADANIENT": 247,
    "ADANIPORTS": 247,
    "APOLLOHOSP": 247,
    "ASIANPAINT": 247,
    "AXISBANK": 247,
    "BAJAJ-AUTO": 247,
    "BAJAJFINSV": 247,
    "BAJFINANCE": 247,
    "BEL": 247,
    "BHARTIARTL": 246,
}
EXPECTED_REVENUE = {
    "ADANIENT": Decimal("100468.61"),
    "ADANIPORTS": Decimal("38735.77"),
    "APOLLOHOSP": Decimal("25228.50"),
    "ASIANPAINT": Decimal("35583.54"),
    "AXISBANK": Decimal("162211.95"),
    "BAJAJ-AUTO": Decimal("62905.00"),
    "BAJAJFINSV": Decimal("150501.77"),
    "BAJFINANCE": Decimal("81989.50"),
    "BEL": Decimal("27610.11"),
    "BHARTIARTL": Decimal("210972.80"),
}
RR_CONFIG = {"atr_multiplier": 1.5, "buffer_percent": 0.01}
SYNTHETIC_SQL = (
    "SELECT COUNT(*) FROM daily_ohlcv "
    "WHERE open=100 AND high=105 AND low=95 AND close=102 AND volume=1000"
)
INVALID_DATE_SQL = (
    "SELECT COUNT(*) FROM daily_ohlcv WHERE trading_date GLOB '????-??-3[2-9]*' "
    "OR trading_date GLOB '????-??-[4-9]*' OR trading_date GLOB '????-??-6*'"
)


def counts(conn: sqlite3.Connection) -> dict:
    out = {}
    for t in [
        "candidate_evaluation_run",
        "candidate_criterion_result",
        "risk_reward_result",
        "fundamental_snapshot",
        "daily_ohlcv",
        "data_import_batch",
        "broker_recommendation",
    ]:
        out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    out["synthetic_ohlcv"] = conn.execute(SYNTHETIC_SQL).fetchone()[0]
    out["invalid_date_ohlcv"] = conn.execute(INVALID_DATE_SQL).fetchone()[0]
    return out


def criterion_fingerprint(conn: sqlite3.Connection, evaluation_ids: list[int]) -> str:
    rows = conn.execute(
        """
        SELECT evaluation_id, result_id, criterion_identifier, observed_value, operator,
               threshold, state, reason, evidence_reference
        FROM candidate_criterion_result
        WHERE evaluation_id IN ({})
        ORDER BY evaluation_id, result_id
        """.format(",".join("?" * len(evaluation_ids))),
        evaluation_ids,
    ).fetchall()
    payload = json.dumps(rows, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_fingerprint(conn: sqlite3.Connection, evaluation_ids: list[int]) -> str:
    rows = conn.execute(
        """
        SELECT evaluation_id, stock_id, classification, config_fingerprint, config_snapshot,
               technical_snapshot_reference, fundamental_snapshot_id
        FROM candidate_evaluation_run
        WHERE evaluation_id IN ({})
        ORDER BY evaluation_id
        """.format(",".join("?" * len(evaluation_ids))),
        evaluation_ids,
    ).fetchall()
    payload = json.dumps(rows, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def rr_would_complete(tech: dict, entry: Decimal) -> bool:
    atr = tech.get("ATR14")
    support = tech.get("Support20")
    resistance = tech.get("Resistance20")
    if atr is None or support is None or resistance is None:
        return False
    stop = entry - (Decimal(str(atr)) * Decimal("1.5"))
    target = Decimal(str(resistance)) * Decimal("0.99")
    return stop > 0 and stop < entry and target > entry


def main() -> None:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = ROOT / "data" / f"swing_trading_backup_{stamp}.db"
    shutil.copy2(DB, backup)

    conn = sqlite3.connect(str(DB))
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    before = counts(conn)
    print("BACKUP", str(backup))
    print("INTEGRITY_BEFORE", integrity)
    print("FK_BEFORE", fk)
    print("COUNTS_BEFORE", json.dumps(before))

    if integrity != "ok" or fk:
        raise SystemExit("STOP_INTEGRITY")
    if (
        before["daily_ohlcv"] != 2469
        or before["fundamental_snapshot"] != 10
        or before["candidate_evaluation_run"] != 13
        or before["candidate_criterion_result"] != 117
        or before["synthetic_ohlcv"] != 0
        or before["invalid_date_ohlcv"] != 0
    ):
        raise SystemExit(json.dumps({"stop": "baseline mismatch", "before": before}))

    historical_ids = [r[0] for r in conn.execute("SELECT evaluation_id FROM candidate_evaluation_run ORDER BY 1")]
    hist_run_fp = run_fingerprint(conn, historical_ids)
    hist_crit_fp = criterion_fingerprint(conn, historical_ids)
    config = json.loads(
        conn.execute("SELECT config_snapshot FROM candidate_evaluation_run WHERE evaluation_id=1").fetchone()[0]
    )
    print("ACTIVE_CONFIG_FINGERPRINT", conn.execute("SELECT config_fingerprint FROM candidate_evaluation_run WHERE evaluation_id=1").fetchone()[0])
    print("HISTORICAL_IDS", historical_ids)
    print("HIST_RUN_FP", hist_run_fp)
    print("HIST_CRIT_FP", hist_crit_fp)
    conn.close()

    db = SessionLocal()
    reports = []
    unknown_treated_as_pass = []
    try:
        for symbol in SYMBOLS:
            stock = db.query(StockMaster).filter(StockMaster.nse_symbol == symbol).one()
            raw = (
                db.query(DailyOhlcv)
                .filter(DailyOhlcv.stock_id == stock.stock_id, DailyOhlcv.series == "EQ")
                .order_by(DailyOhlcv.trading_date.asc())
                .all()
            )
            originals = [(r.open, r.high, r.low, r.close, r.volume) for r in raw]
            if len(raw) != EXPECTED_SESSIONS[symbol]:
                raise RuntimeError(f"{symbol} session count {len(raw)} != {EXPECTED_SESSIONS[symbol]}")
            if any(o == 100 and h == 105 and l == 95 and c == 102 for o, h, l, c, v in originals):
                raise RuntimeError(f"Synthetic OHLC detected for {symbol}")

            adjusted = CorporateActionService.apply_adjustments(db, stock.stock_id, raw)
            after = [(r.open, r.high, r.low, r.close, r.volume) for r in raw]
            if originals != after:
                raise RuntimeError(f"Raw OHLCV mutated for {symbol}")

            tech = TechnicalService.calculate_technical_evidence(adjusted)
            snap = FundamentalService.get_latest_snapshot(db, stock.stock_id)
            if snap is None:
                raise RuntimeError(f"Missing fundamental snapshot for {symbol}")
            fund = FundamentalService.get_metric_evidence(db, snap.snapshot_id)
            revenue = fund.get("revenue") or {}
            if revenue.get("status") != "KNOWN":
                raise RuntimeError(f"{symbol} revenue status {revenue.get('status')}")
            if Decimal(str(revenue.get("value"))) != EXPECTED_REVENUE[symbol]:
                raise RuntimeError(f"{symbol} revenue value changed")

            tech_for_eval = {
                k: tech.get(k)
                for k in [
                    "SMA20",
                    "SMA50",
                    "SMA200",
                    "RSI14",
                    "MACD",
                    "MACD_signal",
                    "MACD_hist",
                    "ATR14",
                    "ATR_percent",
                    "ROC20",
                    "Liquidity20",
                ]
            }
            missing_tech = [k for k, v in tech_for_eval.items() if k in {"SMA20", "SMA50", "SMA200", "RSI14", "MACD", "ATR14", "ROC20", "Liquidity20"} and v is None]
            runs_before_stock = db.query(CandidateEvaluationRun).filter_by(stock_id=stock.stock_id).count()
            run = CandidateService.evaluate_candidate(
                db,
                stock.stock_id,
                config,
                tech_for_eval,
                fund,
                technical_ref=f"prod_ohlcv_{symbol}_{len(raw)}",
                fundamental_ref=snap.snapshot_id,
            )
            db.flush()
            if db.query(CandidateEvaluationRun).filter_by(stock_id=stock.stock_id).count() != runs_before_stock + 1:
                raise RuntimeError("Evaluation overwrite detected")

            criteria = (
                db.query(CandidateCriterionResult)
                .filter_by(evaluation_id=run.evaluation_id)
                .order_by(CandidateCriterionResult.result_id.asc())
                .all()
            )
            grouped = {"PASS": [], "FAIL": [], "UNKNOWN": [], "NOT_APPLICABLE": []}
            crit_rows = []
            for c in criteria:
                grouped.setdefault(c.state, [])
                grouped[c.state].append(c.criterion_identifier)
                if c.state == "UNKNOWN" and run.classification == "FINAL_CANDIDATE":
                    unknown_treated_as_pass.append((symbol, c.criterion_identifier))
                if c.state == "UNKNOWN" and c.state == "PASS":
                    unknown_treated_as_pass.append((symbol, c.criterion_identifier))
                crit_rows.append(
                    {
                        "name": c.criterion_identifier,
                        "actual_value": str(c.observed_value) if c.observed_value is not None else None,
                        "operator": c.operator,
                        "threshold": str(c.threshold) if c.threshold is not None else None,
                        "evidence_state": c.state,
                        "result": c.state,
                        "reason": c.reason,
                        "evidence_reference": c.evidence_reference,
                    }
                )

            if "UNKNOWN" in grouped["PASS"]:
                unknown_treated_as_pass.append((symbol, "PASS_contains_UNKNOWN"))
            if run.classification == "FINAL_CANDIDATE" and grouped["UNKNOWN"]:
                unknown_treated_as_pass.append((symbol, "classification_with_unknown"))

            rr_payload = {
                "applicable": False,
                "reason": "N/A: existing engine requires finite ATR14, Support20, Resistance20, stop < entry, and resistance-derived target > entry",
            }
            close = tech.get("latest_close")
            if close is not None and rr_would_complete(tech, Decimal(str(close))):
                rr = RiskRewardService.calculate_risk_reward(
                    db, run.evaluation_id, RR_CONFIG, tech, float(close)
                )
                db.flush()
                if rr.risk_reward_ratio is None:
                    db.delete(rr)
                    db.flush()
                    rr_payload = {
                        "applicable": False,
                        "reason": "N/A: RR computed incomplete; not persisted (existing no-fabrication rule)",
                    }
                else:
                    ratio = Decimal(str(rr.risk_reward_ratio))
                    if ratio == Decimal("0.6052"):
                        raise RuntimeError(f"{symbol} reused retracted synthetic RR 0.6052")
                    rr_payload = {
                        "applicable": True,
                        "support": str(rr.support),
                        "resistance": str(rr.resistance),
                        "entry": str(rr.entry_reference),
                        "stop": str(rr.stop_loss),
                        "target": str(rr.target),
                        "risk": str(rr.risk_per_share),
                        "reward": str(rr.reward_per_share),
                        "rr": str(rr.risk_reward_ratio),
                        "methodology": json.loads(rr.config_snapshot),
                    }
            else:
                rr_payload["reason"] = (
                    "N/A: ATR14/Support20/Resistance20 missing or stop/target geometry incomplete; "
                    f"close={close} ATR14={tech.get('ATR14')} Support20={tech.get('Support20')} "
                    f"Resistance20={tech.get('Resistance20')}"
                )

            decisive = "All configured mandatory criteria PASS with KNOWN evidence"
            if grouped["UNKNOWN"]:
                decisive = "Mandatory UNKNOWN evidence: " + ",".join(grouped["UNKNOWN"])
            elif grouped["FAIL"]:
                decisive = "Mandatory FAIL: " + ",".join(grouped["FAIL"])
            elif grouped["NOT_APPLICABLE"]:
                decisive = "Mandatory NOT_APPLICABLE: " + ",".join(grouped["NOT_APPLICABLE"])

            reports.append(
                {
                    "symbol": symbol,
                    "stock_id": stock.stock_id,
                    "sessions": tech.get("sessions"),
                    "latest_date": str(tech.get("latest_trading_date")),
                    "latest_close": str(close),
                    "adjustment": tech.get("adjustment_status"),
                    "SMA20": str(tech.get("SMA20")),
                    "SMA50": str(tech.get("SMA50")),
                    "SMA200": str(tech.get("SMA200")),
                    "RSI14": str(tech.get("RSI14")),
                    "MACD": str(tech.get("MACD")),
                    "MACD_signal": str(tech.get("MACD_signal")),
                    "MACD_hist": str(tech.get("MACD_hist")),
                    "ATR14": str(tech.get("ATR14")),
                    "ROC20": str(tech.get("ROC20")),
                    "Breakout20": tech.get("Breakout20_status"),
                    "Liquidity20": str(tech.get("Liquidity20")),
                    "revenue": str(revenue.get("value")),
                    "revenue_status": revenue.get("status"),
                    "entity_type": snap.entity_type,
                    "period": snap.financial_period,
                    "missing_tech": missing_tech,
                    "evaluation_id": run.evaluation_id,
                    "classification": run.classification,
                    "config_fingerprint": run.config_fingerprint,
                    "criteria": crit_rows,
                    "pass": grouped["PASS"],
                    "fail": grouped["FAIL"],
                    "unknown": grouped["UNKNOWN"],
                    "not_applicable": grouped["NOT_APPLICABLE"],
                    "decisive": decisive,
                    "mandatory_complete": not grouped["UNKNOWN"] and not grouped["NOT_APPLICABLE"],
                    "unknown_ne_pass": "UNKNOWN" not in grouped["PASS"] and not (
                        run.classification == "FINAL_CANDIDATE" and grouped["UNKNOWN"]
                    ),
                    "rr": rr_payload,
                }
            )

        if unknown_treated_as_pass:
            raise RuntimeError(f"UNKNOWN treated as PASS: {unknown_treated_as_pass}")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    conn = sqlite3.connect(str(DB))
    after = counts(conn)
    after_ids = [r[0] for r in conn.execute("SELECT evaluation_id FROM candidate_evaluation_run ORDER BY 1")]
    still_hist = all(i in after_ids for i in historical_ids)
    hist_run_fp_after = run_fingerprint(conn, historical_ids)
    hist_crit_fp_after = criterion_fingerprint(conn, historical_ids)
    new_ids = [i for i in after_ids if i not in historical_ids]
    latest = dict(
        conn.execute(
            """
            SELECT s.nse_symbol, MAX(e.evaluation_id)
            FROM candidate_evaluation_run e
            JOIN stock_master s ON s.stock_id=e.stock_id
            GROUP BY s.nse_symbol
            """
        )
    )
    new_by_symbol = {}
    for r in reports:
        new_by_symbol[r["symbol"]] = r["evaluation_id"]
    latest_is_new = all(latest[sym] == new_by_symbol[sym] for sym in SYMBOLS)
    revenues_after = {
        r[0]: Decimal(str(r[1]))
        for r in conn.execute(
            """
            SELECT s.nse_symbol, fm.metric_value
            FROM fundamental_snapshot fs
            JOIN stock_master s ON s.stock_id=fs.stock_id
            JOIN fundamental_metric fm ON fm.snapshot_id=fs.snapshot_id AND fm.metric_name='revenue'
            """
        )
    }
    integrity_after = conn.execute("PRAGMA integrity_check").fetchone()[0]
    fk_after = conn.execute("PRAGMA foreign_key_check").fetchall()
    print("COUNTS_AFTER", json.dumps(after))
    print("INTEGRITY_AFTER", integrity_after)
    print("FK_AFTER", fk_after)
    print("HISTORICAL_PRESERVED", still_hist and hist_run_fp_after == hist_run_fp and hist_crit_fp_after == hist_crit_fp)
    print("NEW_IDS", new_ids)
    print("LATEST_IS_NEW", latest_is_new)
    print("FUNDAMENTALS_UNCHANGED", revenues_after == EXPECTED_REVENUE)
    conn.close()

    out = {
        "backup": str(backup),
        "before": before,
        "after": after,
        "historical_ids": historical_ids,
        "new_ids": new_ids,
        "historical_preserved": still_hist and hist_run_fp_after == hist_run_fp and hist_crit_fp_after == hist_crit_fp,
        "latest_is_new": latest_is_new,
        "fundamentals_unchanged": revenues_after == EXPECTED_REVENUE,
        "integrity_after": integrity_after,
        "fk_after": fk_after,
        "totals": dict(Counter(r["classification"] for r in reports)),
        "reports": reports,
    }
    report_path = ROOT / "manual_inputs" / "fundamentals" / f"batch_a_candidate_reeval_{stamp}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print("REPORT", str(report_path))
    for r in reports:
        print(
            "STOCK",
            r["symbol"],
            r["classification"],
            "eval",
            r["evaluation_id"],
            "unknown_ne_pass",
            r["unknown_ne_pass"],
            "rr",
            r["rr"].get("rr") if r["rr"].get("applicable") else r["rr"].get("reason"),
        )
    print("TOTALS", out["totals"])
    if not out["historical_preserved"] or not latest_is_new or not out["fundamentals_unchanged"]:
        raise SystemExit("STOP_POST_EVAL_FORENSICS")
    if after["candidate_evaluation_run"] != 23:
        raise SystemExit(f"STOP_RUN_COUNT {after['candidate_evaluation_run']}")
    if after["daily_ohlcv"] != 2469 or after["fundamental_snapshot"] != 10 or after["broker_recommendation"] != 5:
        raise SystemExit("STOP_CORE_COUNTS")


if __name__ == "__main__":
    main()
