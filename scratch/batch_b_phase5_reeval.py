"""Controlled Batch B Phase 5 re-evaluation.

Creates exactly one new Phase 5 evaluation per Batch B stock.
Does not overwrite historical runs, OHLCV, fundamentals, or candidate configuration.
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
from app.schema_readiness import guard_script_write  # noqa: E402  (refuses a stale schema before any write)
from app.models import (
    CandidateCriterionResult,
    CandidateEvaluationRun,
    DailyOhlcv,
    FundamentalSnapshot,
    StockMaster,
)
from app.services.candidate_config import (
    ACTIVE_CANDIDATE_CONFIG,
    LEGACY_BATCH_A_POST_IMPORT_CONFIG,
    PHASE5_TREND_SCREEN_V1,
)
from app.services.candidate_service import CandidateService
from app.services.corporate_action_service import CorporateActionService
from app.services.evidence_service import EvidenceService
from app.services.fundamental_service import FundamentalService
from app.services.risk_reward_service import RiskRewardService
from app.services.technical_service import TechnicalService

REQUIRED_FP = "146408d7d5de3ce55acd5465d2c788acca9d8e1875c21e1af470151a3f0f97fe"
LEGACY_FP = "9ac50fd3f34e2242b2a635eb8a84c66d0316f757caaa20944d59d185d7b64a18"
SYMBOLS = [
    "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
    "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO",
]
EXPECTED_REVENUE = {
    "CIPLA": Decimal("28162.59"),
    "COALINDIA": Decimal("168400.29"),
    "DRREDDY": Decimal("33700.2"),
    "EICHERMOT": Decimal("23407.56"),
    "ETERNAL": Decimal("54364"),
    "GRASIM": Decimal("175430.74"),
    "HCLTECH": Decimal("130144"),
    "HDFCBANK": Decimal("495462.81"),
    "HDFCLIFE": Decimal("98770.38"),
    "HINDALCO": Decimal("274944"),
}
EXPECTED_ENTITY = {
    "CIPLA": "ORDINARY",
    "COALINDIA": "ORDINARY",
    "DRREDDY": "ORDINARY",
    "EICHERMOT": "ORDINARY",
    "ETERNAL": "ORDINARY",
    "GRASIM": "ORDINARY",
    "HCLTECH": "ORDINARY",
    "HDFCBANK": "BANK",
    "HDFCLIFE": "INSURANCE",
    "HINDALCO": "ORDINARY",
}
INSURANCE_LINE = "Total Income (Policyholders' Account)"
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


def rr_fingerprint(conn: sqlite3.Connection, evaluation_ids: list[int]) -> str:
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


def expected_from_policy(grouped: dict) -> str:
    if grouped["UNKNOWN"]:
        return "INSUFFICIENT_DATA"
    mandatory_fail = [c for c in grouped["FAIL"] if c != "sma50_gt_sma200"]
    if mandatory_fail:
        return "REJECTED"
    if "sma50_gt_sma200" in grouped["FAIL"]:
        return "WATCH"
    return "FINAL_CANDIDATE"


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
    guard_script_write(DB)
    guard_script_write(SessionLocal)
    if ACTIVE_CANDIDATE_CONFIG is not PHASE5_TREND_SCREEN_V1:
        raise SystemExit("STOP_ACTIVE_CONFIG_IDENTITY")
    fp = CandidateService.get_config_fingerprint(ACTIVE_CANDIDATE_CONFIG)
    print("ACTIVE_CONFIG", PHASE5_TREND_SCREEN_V1["name"], PHASE5_TREND_SCREEN_V1["version"])
    print("ACTIVE_FINGERPRINT", fp)
    if fp != REQUIRED_FP:
        raise SystemExit(f"STOP_FINGERPRINT_MISMATCH {fp}")
    if CandidateService.get_config_fingerprint(LEGACY_BATCH_A_POST_IMPORT_CONFIG) != LEGACY_FP:
        raise SystemExit("STOP_LEGACY_FINGERPRINT_CHANGED")
    if CandidateService.get_config_fingerprint(PHASE5_TREND_SCREEN_V1) != REQUIRED_FP:
        raise SystemExit("STOP_PHASE5_CONSTANT_CHANGED")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = ROOT / "data" / "safety_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"swing_trading_PRE_PHASE5_BATCH_B_{stamp}.db"
    pre_sha = hashlib.sha256(DB.read_bytes()).hexdigest()
    shutil.copy2(DB, backup)
    backup_sha = hashlib.sha256(backup.read_bytes()).hexdigest()
    if backup_sha != pre_sha:
        raise SystemExit("STOP_BACKUP_SHA")
    print("BACKUP", str(backup))
    print("BACKUP_SHA", backup_sha)

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
        before["daily_ohlcv"] != 4939
        or before["fundamental_snapshot"] != 20
        or before["candidate_evaluation_run"] != 33
        or before["candidate_criterion_result"] != 297
        or before["risk_reward_result"] != 29
        or before["broker_recommendation"] != 5
        or before["synthetic_ohlcv"] != 0
    ):
        raise SystemExit(json.dumps({"stop": "baseline mismatch", "before": before}))

    historical_ids = [r[0] for r in conn.execute("SELECT evaluation_id FROM candidate_evaluation_run ORDER BY 1")]
    if historical_ids != list(range(1, 34)):
        raise SystemExit(f"STOP_HISTORICAL_IDS {historical_ids}")
    hist_run_fp = run_fingerprint(conn, historical_ids)
    hist_crit_fp = criterion_fingerprint(conn, historical_ids)
    hist_rr_fp = rr_fingerprint(conn, historical_ids)
    existing_b = conn.execute(
        """
        SELECT COUNT(*) FROM candidate_evaluation_run e
        JOIN stock_master s ON s.stock_id=e.stock_id
        WHERE s.nse_symbol IN ({})
        """.format(",".join("?" * len(SYMBOLS))),
        SYMBOLS,
    ).fetchone()[0]
    if existing_b != 0:
        raise SystemExit(f"STOP_BATCH_B_ALREADY_EVALUATED {existing_b}")
    hist_rr_count = conn.execute("SELECT COUNT(*) FROM risk_reward_result").fetchone()[0]
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
            if len(raw) < 200:
                raise RuntimeError(f"{symbol} sessions {len(raw)} < 200")
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
            if snap.entity_type != EXPECTED_ENTITY[symbol]:
                raise RuntimeError(f"{symbol} entity {snap.entity_type}")
            if snap.is_superseded:
                raise RuntimeError(f"{symbol} latest snapshot superseded")
            fund = FundamentalService.get_metric_evidence(db, snap.snapshot_id)
            revenue = fund.get("revenue") or {}
            if revenue.get("status") != "KNOWN":
                raise RuntimeError(f"{symbol} revenue status {revenue.get('status')}")
            if Decimal(str(revenue.get("value"))) != EXPECTED_REVENUE[symbol]:
                raise RuntimeError(f"{symbol} revenue value changed")
            if symbol == "HDFCLIFE":
                if snap.entity_type != "INSURANCE":
                    raise RuntimeError("HDFCLIFE entity not INSURANCE")
                if snap.source_line_item != INSURANCE_LINE:
                    raise RuntimeError(f"HDFCLIFE line {snap.source_line_item}")
                if "Shareholders" in (snap.source_line_item or ""):
                    raise RuntimeError("HDFCLIFE shareholders line used")

            tech_for_eval = {
                k: tech.get(k)
                for k in [
                    "SMA20", "SMA50", "SMA200", "ATR14", "latest_close", "sessions",
                    "RSI14", "MACD", "MACD_signal", "ROC20", "Liquidity20",
                    "Support20", "Resistance20", "Breakout20_status",
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
            snap_json = json.loads(run.config_snapshot)
            if snap_json["name"] != "phase5_trend_screen_v1" or snap_json["version"] != "phase5-v1":
                raise RuntimeError(f"{symbol} config snapshot mutated")

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
                if c.state == "PASS" and "UNKNOWN" in (c.reason or ""):
                    raise RuntimeError(f"{symbol} UNKNOWN reason stored as PASS")
                crit_rows.append(
                    {
                        "name": c.criterion_identifier,
                        "actual_value": str(c.observed_value) if c.observed_value is not None else None,
                        "operator": c.operator,
                        "threshold": str(c.threshold) if c.threshold is not None else None,
                        "evidence_state": c.state,
                        "reason": c.reason,
                    }
                )

            expected = expected_from_policy(grouped)
            if run.classification != expected:
                raise RuntimeError(f"{symbol} classification {run.classification} != policy {expected}")
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

            reports.append(
                {
                    "symbol": symbol,
                    "evaluation_id": run.evaluation_id,
                    "classification": run.classification,
                    "expected": expected,
                    "config_fingerprint": run.config_fingerprint,
                    "fundamental_snapshot_id": snap.snapshot_id,
                    "entity_type": snap.entity_type,
                    "source_line_item": snap.source_line_item,
                    "sessions": tech.get("sessions"),
                    "latest_close": str(close),
                    "SMA50": str(tech.get("SMA50")),
                    "SMA200": str(tech.get("SMA200")),
                    "revenue": str(revenue.get("value")),
                    "revenue_status": revenue.get("status"),
                    "criteria": crit_rows,
                    "pass": grouped["PASS"],
                    "fail": grouped["FAIL"],
                    "unknown": grouped["UNKNOWN"],
                    "decisive": EvidenceService.decisive_reason(run.classification, criteria),
                    "rr": rr_payload,
                }
            )

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
    new_ids = [i for i in after_ids if i not in historical_ids]
    hist_run_fp_after = run_fingerprint(conn, historical_ids)
    hist_crit_fp_after = criterion_fingerprint(conn, historical_ids)
    hist_rr_fp_after = rr_fingerprint(conn, historical_ids)
    hist_rr_count_now = conn.execute(
        "SELECT COUNT(*) FROM risk_reward_result WHERE evaluation_id IN ({})".format(
            ",".join("?" * len(historical_ids))
        ),
        historical_ids,
    ).fetchone()[0]
    latest_ok = True
    latest_rows = []
    for symbol, eval_id in zip(SYMBOLS, [r["evaluation_id"] for r in reports]):
        latest = conn.execute(
            """
            SELECT e.evaluation_id FROM candidate_evaluation_run e
            JOIN stock_master s ON s.stock_id=e.stock_id
            WHERE s.nse_symbol=?
            ORDER BY e.evaluation_date DESC, e.evaluation_id DESC
            LIMIT 1
            """,
            (symbol,),
        ).fetchone()[0]
        max_id = conn.execute(
            """
            SELECT MAX(e.evaluation_id) FROM candidate_evaluation_run e
            JOIN stock_master s ON s.stock_id=e.stock_id
            WHERE s.nse_symbol=?
            """,
            (symbol,),
        ).fetchone()[0]
        latest_rows.append({"symbol": symbol, "new_id": eval_id, "latest": latest, "max_id": max_id})
        if latest != eval_id or max_id != eval_id:
            latest_ok = False
    hdfclife_row = conn.execute(
        """
        SELECT e.evaluation_id, e.classification, e.fundamental_snapshot_id,
               fs.entity_type, fs.source_line_item, fm.metric_value, fm.status
        FROM candidate_evaluation_run e
        JOIN stock_master s ON s.stock_id=e.stock_id
        JOIN fundamental_snapshot fs ON fs.snapshot_id=e.fundamental_snapshot_id
        JOIN fundamental_metric fm ON fm.snapshot_id=fs.snapshot_id AND fm.metric_name='revenue'
        WHERE s.nse_symbol='HDFCLIFE'
        ORDER BY e.evaluation_id DESC LIMIT 1
        """
    ).fetchone()
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
    conn.close()

    historical_preserved = (
        all(i in after_ids for i in historical_ids)
        and hist_run_fp_after == hist_run_fp
        and hist_crit_fp_after == hist_crit_fp
        and hist_rr_fp_after == hist_rr_fp
        and hist_rr_count_now == hist_rr_count
    )
    mismatches = [r for r in reports if r["classification"] != r["expected"]]
    one_each = len(new_ids) == 10 and len({r["evaluation_id"] for r in reports}) == 10
    defects = []
    if not historical_preserved:
        defects.append("historical runs mutated")
    if not latest_ok:
        defects.append("latest selection not new evaluation")
    if not one_each:
        defects.append("not exactly one new run per Batch B stock")
    if after["candidate_evaluation_run"] != 43:
        defects.append(f"run count {after['candidate_evaluation_run']}")
    if after["daily_ohlcv"] != 4939:
        defects.append("OHLCV changed")
    if after["fundamental_snapshot"] != 20:
        defects.append("fundamentals changed")
    if after["broker_recommendation"] != 5:
        defects.append("broker recommendations changed")
    if after["synthetic_ohlcv"] != 0 or integrity_after != "ok" or fk_after:
        defects.append("db health")
    if revenues_after != EXPECTED_REVENUE:
        defects.append("revenue values changed")
    if hdfclife_row is None or hdfclife_row[3] != "INSURANCE" or hdfclife_row[4] != INSURANCE_LINE:
        defects.append("HDFCLIFE insurance evidence not used")
    if mismatches:
        defects.append("classification mismatch")
    unknown_as_pass = [u for u in unknown_treated_as_pass if u[2] == "FINAL_CANDIDATE"]
    if unknown_as_pass:
        defects.append(f"UNKNOWN treated as PASS: {unknown_as_pass}")

    out = {
        "backup": str(backup),
        "backup_sha256": backup_sha,
        "fingerprint": fp,
        "before": before,
        "after": after,
        "historical_ids": historical_ids,
        "new_ids": new_ids,
        "historical_preserved": historical_preserved,
        "latest_selection": latest_rows,
        "latest_ok": latest_ok,
        "hdfclife": list(hdfclife_row) if hdfclife_row else None,
        "integrity_after": integrity_after,
        "fk_after": fk_after,
        "totals": dict(Counter(r["classification"] for r in reports)),
        "mismatches": mismatches,
        "reports": reports,
        "defects": defects,
        "unknown_treated_as_pass": unknown_treated_as_pass,
    }
    report_path = ROOT / "manual_inputs" / "fundamentals" / f"batch_b_phase5_reeval_{stamp}.json"
    report_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print("REPORT", str(report_path))
    print("COUNTS_AFTER", json.dumps(after))
    print("HISTORICAL_PRESERVED", historical_preserved)
    print("NEW_IDS", new_ids)
    print("LATEST_OK", latest_ok)
    print("HDFCLIFE", hdfclife_row)
    for r in reports:
        print(
            "STOCK", r["symbol"], r["classification"], "eval", r["evaluation_id"],
            "close", r["latest_close"], "SMA50", r["SMA50"], "SMA200", r["SMA200"],
            "rev", r["revenue"], r["revenue_status"], "decisive", r["decisive"],
            "rr", r["rr"].get("rr") if r["rr"].get("applicable") else "N/A",
        )
    print("TOTALS", out["totals"])
    print("DEFECTS", defects)
    if defects:
        raise SystemExit("PHASE 5 BATCH B RE-EVALUATION FAILED — STOP")


if __name__ == "__main__":
    main()
