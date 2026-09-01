"""Controlled Batch A Phase 5 re-evaluation.

Creates exactly one new Phase 5 evaluation per Batch A stock.
Does not overwrite historical runs, OHLCV, or fundamentals.
Does not edit candidate configuration.
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
from app.services.candidate_config import (
    ACTIVE_CANDIDATE_CONFIG,
    LEGACY_BATCH_A_POST_IMPORT_CONFIG,
    PHASE5_TREND_SCREEN_V1,
)
from app.services.candidate_service import CandidateService
from app.services.corporate_action_service import CorporateActionService
from app.services.fundamental_service import FundamentalService
from app.services.risk_reward_service import RiskRewardService
from app.services.technical_service import TechnicalService

REQUIRED_FP = "146408d7d5de3ce55acd5465d2c788acca9d8e1875c21e1af470151a3f0f97fe"
LEGACY_FP = "9ac50fd3f34e2242b2a635eb8a84c66d0316f757caaa20944d59d185d7b64a18"
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
EXPECTED_CLASS = {
    "ADANIENT": "REJECTED",
    "ADANIPORTS": "REJECTED",
    "APOLLOHOSP": "REJECTED",
    "ASIANPAINT": "FINAL_CANDIDATE",
    "AXISBANK": "REJECTED",
    "BAJAJ-AUTO": "FINAL_CANDIDATE",
    "BAJAJFINSV": "WATCH",
    "BAJFINANCE": "FINAL_CANDIDATE",
    "BEL": "WATCH",
    "BHARTIARTL": "WATCH",
}
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
REQUIRED_CRITERIA = [
    "SMA20_known",
    "SMA50_known",
    "SMA200_known",
    "ATR14_known",
    "sma200_history",
    "revenue_known",
    "revenue_positive",
    "close_gt_sma50",
    "sma50_gt_sma200",
]
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
    return hashlib.sha256(json.dumps(rows, default=str, separators=(",", ":")).encode()).hexdigest()


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
    return hashlib.sha256(json.dumps(rows, default=str, separators=(",", ":")).encode()).hexdigest()


def rr_fingerprint(conn: sqlite3.Connection, evaluation_ids: list[int] | None = None) -> str:
    if evaluation_ids:
        rows = conn.execute(
            """
            SELECT result_id, evaluation_id, support, resistance, entry_reference, target,
                   stop_loss, risk_per_share, reward_per_share, risk_reward_ratio, config_snapshot
            FROM risk_reward_result
            WHERE evaluation_id IN ({})
            ORDER BY result_id
            """.format(",".join("?" * len(evaluation_ids))),
            evaluation_ids,
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT result_id, evaluation_id, support, resistance, entry_reference, target,
                   stop_loss, risk_per_share, reward_per_share, risk_reward_ratio, config_snapshot
            FROM risk_reward_result
            ORDER BY result_id
            """
        ).fetchall()
    return hashlib.sha256(json.dumps(rows, default=str, separators=(",", ":")).encode()).hexdigest()


def rr_would_complete(tech: dict, entry: Decimal) -> bool:
    atr = tech.get("ATR14")
    support = tech.get("Support20")
    resistance = tech.get("Resistance20")
    if atr is None or support is None or resistance is None:
        return False
    stop = entry - (Decimal(str(atr)) * Decimal("1.5"))
    target = Decimal(str(resistance)) * Decimal("0.99")
    return stop > 0 and stop < entry and target > entry


def decisive_rule(grouped: dict, classification: str) -> str:
    if grouped["UNKNOWN"]:
        return "INSUFFICIENT_DATA: " + ",".join(grouped["UNKNOWN"])
    if "revenue_positive" in grouped["FAIL"]:
        return "REJECTED: revenue_positive FAIL"
    if "close_gt_sma50" in grouped["FAIL"]:
        return "REJECTED: close_gt_sma50 FAIL"
    mandatory_fail = [c for c in grouped["FAIL"] if c != "sma50_gt_sma200"]
    if mandatory_fail:
        return f"{classification}: mandatory FAIL {','.join(mandatory_fail)}"
    if "sma50_gt_sma200" in grouped["FAIL"]:
        return "WATCH: sma50_gt_sma200 FAIL (optional confirmation)"
    return "FINAL_CANDIDATE: close > SMA50 and SMA50 > SMA200"


def main() -> None:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = ROOT / "data" / f"swing_trading_backup_{stamp}.db"
    shutil.copy2(DB, backup)
    print("BACKUP", str(backup))

    conn = sqlite3.connect(str(DB))
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    before = counts(conn)
    print("INTEGRITY_BEFORE", integrity)
    print("FK_BEFORE", fk)
    print("COUNTS_BEFORE", json.dumps(before))
    if integrity != "ok" or fk:
        raise SystemExit("STOP_INTEGRITY")
    if (
        before["daily_ohlcv"] != 2469
        or before["fundamental_snapshot"] != 10
        or before["candidate_evaluation_run"] != 23
        or before["candidate_criterion_result"] != 207
        or before["risk_reward_result"] != 20
        or before["broker_recommendation"] != 5
        or before["synthetic_ohlcv"] != 0
        or before["invalid_date_ohlcv"] != 0
    ):
        raise SystemExit(json.dumps({"stop": "baseline mismatch", "before": before}))

    historical_ids = [r[0] for r in conn.execute("SELECT evaluation_id FROM candidate_evaluation_run ORDER BY 1")]
    if historical_ids != list(range(1, 24)):
        raise SystemExit(f"STOP_HISTORICAL_IDS {historical_ids}")
    hist_run_fp = run_fingerprint(conn, historical_ids)
    hist_crit_fp = criterion_fingerprint(conn, historical_ids)
    hist_rr_fp = rr_fingerprint(conn, historical_ids)
    old_fps = {r[0] for r in conn.execute("SELECT DISTINCT config_fingerprint FROM candidate_evaluation_run")}
    print("HISTORICAL_IDS", historical_ids)
    print("HIST_RUN_FP", hist_run_fp)
    print("HIST_CRIT_FP", hist_crit_fp)
    print("HIST_RR_FP", hist_rr_fp)
    print("EXISTING_FINGERPRINTS", sorted(old_fps))
    if old_fps != {LEGACY_FP}:
        raise SystemExit("STOP_UNEXPECTED_EXISTING_FINGERPRINT")
    conn.close()

    if ACTIVE_CANDIDATE_CONFIG is not PHASE5_TREND_SCREEN_V1:
        raise SystemExit("STOP_ACTIVE_CONFIG_IDENTITY")
    fp = CandidateService.get_config_fingerprint(ACTIVE_CANDIDATE_CONFIG)
    print("ACTIVE_CONFIG", json.dumps(ACTIVE_CANDIDATE_CONFIG, sort_keys=True, indent=2))
    print("ACTIVE_FINGERPRINT", fp)
    if fp != REQUIRED_FP:
        raise SystemExit(f"STOP_FINGERPRINT_MISMATCH {fp}")
    if CandidateService.get_config_fingerprint(LEGACY_BATCH_A_POST_IMPORT_CONFIG) != LEGACY_FP:
        raise SystemExit("STOP_LEGACY_FINGERPRINT_CHANGED")

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
            after_raw = [(r.open, r.high, r.low, r.close, r.volume) for r in raw]
            if originals != after_raw:
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
                    "ATR14",
                    "latest_close",
                    "sessions",
                    "RSI14",
                    "MACD",
                    "MACD_signal",
                    "ROC20",
                    "Liquidity20",
                    "Support20",
                    "Resistance20",
                    "Breakout20_status",
                ]
            }
            runs_before_stock = db.query(CandidateEvaluationRun).filter_by(stock_id=stock.stock_id).count()
            run = CandidateService.evaluate_candidate(
                db,
                stock.stock_id,
                ACTIVE_CANDIDATE_CONFIG,
                tech_for_eval,
                fund,
                technical_ref=f"phase5_prod_ohlcv_{symbol}_{len(raw)}",
                fundamental_ref=snap.snapshot_id,
            )
            db.flush()
            if db.query(CandidateEvaluationRun).filter_by(stock_id=stock.stock_id).count() != runs_before_stock + 1:
                raise RuntimeError("Evaluation overwrite detected")
            if run.config_fingerprint != REQUIRED_FP:
                raise RuntimeError(f"{symbol} persisted fingerprint {run.config_fingerprint}")

            criteria = (
                db.query(CandidateCriterionResult)
                .filter_by(evaluation_id=run.evaluation_id)
                .order_by(CandidateCriterionResult.result_id.asc())
                .all()
            )
            ids = [c.criterion_identifier for c in criteria]
            if ids != REQUIRED_CRITERIA:
                raise RuntimeError(f"{symbol} criterion ids {ids}")
            grouped = {"PASS": [], "FAIL": [], "UNKNOWN": [], "NOT_APPLICABLE": []}
            crit_rows = []
            for c in criteria:
                grouped.setdefault(c.state, [])
                grouped[c.state].append(c.criterion_identifier)
                if c.state == "UNKNOWN":
                    unknown_treated_as_pass.append((symbol, c.criterion_identifier, run.classification))
                    if run.classification == "FINAL_CANDIDATE":
                        raise RuntimeError(f"{symbol} UNKNOWN became FINAL_CANDIDATE via {c.criterion_identifier}")
                crit_rows.append(
                    {
                        "name": c.criterion_identifier,
                        "actual_value": str(c.observed_value) if c.observed_value is not None else None,
                        "operator": c.operator,
                        "threshold": str(c.threshold) if c.threshold is not None else None,
                        "evidence_state": c.state,
                        "reason": c.reason,
                        "evidence_reference": c.evidence_reference,
                    }
                )
            if any(c.state == "PASS" and "UNKNOWN" in (c.reason or "") for c in criteria):
                raise RuntimeError(f"{symbol} UNKNOWN reason stored as PASS")

            if run.classification == "WATCH" and "sma50_gt_sma200" not in grouped["FAIL"]:
                raise RuntimeError(f"{symbol} WATCH without optional confirmation FAIL")
            if run.classification == "REJECTED" and "sma50_gt_sma200" in grouped["FAIL"] and not (
                set(grouped["FAIL"]) - {"sma50_gt_sma200"}
            ) and not grouped["UNKNOWN"]:
                raise RuntimeError(f"{symbol} optional confirmation FAIL classified REJECTED")

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
                    }
            else:
                rr_payload["reason"] = (
                    "N/A: ATR14/Support20/Resistance20 missing or stop/target geometry incomplete; "
                    f"close={close} ATR14={tech.get('ATR14')} Support20={tech.get('Support20')} "
                    f"Resistance20={tech.get('Resistance20')}"
                )

            expected = EXPECTED_CLASS[symbol]
            mismatch = None
            if run.classification != expected:
                mismatch = {
                    "expected": expected,
                    "actual": run.classification,
                    "latest_close": str(close),
                    "SMA50": str(tech.get("SMA50")),
                    "SMA200": str(tech.get("SMA200")),
                    "revenue": str(revenue.get("value")),
                    "decisive_rule": decisive_rule(grouped, run.classification),
                }

            reports.append(
                {
                    "symbol": symbol,
                    "evaluation_id": run.evaluation_id,
                    "classification": run.classification,
                    "expected": expected,
                    "config_fingerprint": run.config_fingerprint,
                    "sessions": tech.get("sessions"),
                    "latest_close": str(close),
                    "SMA20": str(tech.get("SMA20")),
                    "SMA50": str(tech.get("SMA50")),
                    "SMA200": str(tech.get("SMA200")),
                    "ATR14": str(tech.get("ATR14")),
                    "revenue": str(revenue.get("value")),
                    "revenue_status": revenue.get("status"),
                    "criteria": crit_rows,
                    "pass": grouped["PASS"],
                    "fail": grouped["FAIL"],
                    "unknown": grouped["UNKNOWN"],
                    "not_applicable": grouped["NOT_APPLICABLE"],
                    "decisive": decisive_rule(grouped, run.classification),
                    "mismatch": mismatch,
                    "rr": rr_payload,
                }
            )

        # UNKNOWN rows are allowed for INSUFFICIENT_DATA; they must never be PASS.
        bad_unknown = [u for u in unknown_treated_as_pass if u[2] == "FINAL_CANDIDATE"]
        if bad_unknown:
            raise RuntimeError(f"UNKNOWN treated as PASS: {bad_unknown}")
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
    hist_rr_fp_after = rr_fingerprint(conn, historical_ids)
    hist_rr_count_now = conn.execute(
        "SELECT COUNT(*) FROM risk_reward_result WHERE evaluation_id IN ({})".format(
            ",".join("?" * len(historical_ids))
        ),
        historical_ids,
    ).fetchone()[0]
    new_ids = [i for i in after_ids if i not in historical_ids]
    new_fps = {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT config_fingerprint FROM candidate_evaluation_run WHERE evaluation_id IN ({})".format(
                ",".join("?" * len(new_ids))
            ),
            new_ids,
        )
    }
    old_fps_after = {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT config_fingerprint FROM candidate_evaluation_run WHERE evaluation_id IN ({})".format(
                ",".join("?" * len(historical_ids))
            ),
            historical_ids,
        )
    }
    revenues_after = {
        r[0]: Decimal(str(r[1]))
        for r in conn.execute(
            """
            SELECT s.nse_symbol, fm.metric_value
            FROM fundamental_snapshot fs
            JOIN stock_master s ON s.stock_id=fs.stock_id
            JOIN fundamental_metric fm ON fm.snapshot_id=fs.snapshot_id AND fm.metric_name='revenue'
            WHERE fs.is_superseded = 0
            """
        )
    }
    integrity_after = conn.execute("PRAGMA integrity_check").fetchone()[0]
    fk_after = conn.execute("PRAGMA foreign_key_check").fetchall()
    print("COUNTS_AFTER", json.dumps(after))
    print("INTEGRITY_AFTER", integrity_after)
    print("FK_AFTER", fk_after)
    historical_preserved = (
        still_hist
        and hist_run_fp_after == hist_run_fp
        and hist_crit_fp_after == hist_crit_fp
        and hist_rr_fp_after == hist_rr_fp
        and hist_rr_count_now == 20
    )
    print("HISTORICAL_PRESERVED", historical_preserved)
    print("NEW_IDS", new_ids)
    print("NEW_FINGERPRINTS", sorted(new_fps))
    print("OLD_FINGERPRINTS_AFTER", sorted(old_fps_after))
    print("FUNDAMENTALS_UNCHANGED", revenues_after == EXPECTED_REVENUE)
    print("HIST_RR_COUNT_NOW", hist_rr_count_now)
    conn.close()

    mismatches = [r for r in reports if r["mismatch"]]
    out = {
        "backup": str(backup),
        "before": before,
        "after": after,
        "historical_ids": historical_ids,
        "new_ids": new_ids,
        "historical_preserved": historical_preserved,
        "old_fingerprints_after": sorted(old_fps_after),
        "new_fingerprints": sorted(new_fps),
        "fundamentals_unchanged": revenues_after == EXPECTED_REVENUE,
        "integrity_after": integrity_after,
        "fk_after": fk_after,
        "totals": dict(Counter(r["classification"] for r in reports)),
        "mismatches": mismatches,
        "reports": reports,
        "hist_rr_count_now": hist_rr_count_now,
    }
    report_path = ROOT / "manual_inputs" / "fundamentals" / f"batch_a_phase5_reeval_{stamp}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print("REPORT", str(report_path))
    for r in reports:
        print(
            "STOCK",
            r["symbol"],
            r["classification"],
            "expected",
            r["expected"],
            "eval",
            r["evaluation_id"],
            "close",
            r["latest_close"],
            "SMA50",
            r["SMA50"],
            "SMA200",
            r["SMA200"],
            "decisive",
            r["decisive"],
            "rr",
            r["rr"].get("rr") if r["rr"].get("applicable") else r["rr"].get("reason"),
        )
    print("TOTALS", out["totals"])
    print("MISMATCHES", json.dumps(mismatches, default=str))
    if not out["historical_preserved"] or old_fps_after != {LEGACY_FP} or new_fps != {REQUIRED_FP}:
        raise SystemExit("STOP_POST_EVAL_FORENSICS")
    if after["candidate_evaluation_run"] != 33:
        raise SystemExit(f"STOP_RUN_COUNT {after['candidate_evaluation_run']}")
    if after["daily_ohlcv"] != 2469 or after["fundamental_snapshot"] != 10 or after["broker_recommendation"] != 5:
        raise SystemExit("STOP_CORE_COUNTS")
    if after["synthetic_ohlcv"] != 0 or integrity_after != "ok" or fk_after:
        raise SystemExit("STOP_DB_HEALTH")
    if revenues_after != EXPECTED_REVENUE:
        raise SystemExit("STOP_REVENUE")


if __name__ == "__main__":
    main()
