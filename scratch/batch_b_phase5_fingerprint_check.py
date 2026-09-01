"""Verify Phase 5 fingerprint and inspect current evaluation baseline. Read-only."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(r"D:\Swing Trading")
sys.path.insert(0, str(ROOT / "backend"))

from app.services.candidate_config import (
    ACTIVE_CANDIDATE_CONFIG,
    PHASE5_TREND_SCREEN_V1,
    LEGACY_BATCH_A_POST_IMPORT_CONFIG,
)
from app.services.candidate_service import CandidateService

REQUIRED_FP = "146408d7d5de3ce55acd5465d2c788acca9d8e1875c21e1af470151a3f0f97fe"
BATCH_B = [
    "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
    "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO",
]


def main() -> None:
    fp = CandidateService.get_config_fingerprint(PHASE5_TREND_SCREEN_V1)
    active_fp = CandidateService.get_config_fingerprint(ACTIVE_CANDIDATE_CONFIG)
    print("NAME", PHASE5_TREND_SCREEN_V1["name"])
    print("VERSION", PHASE5_TREND_SCREEN_V1["version"])
    print("ACTIVE_IS_PHASE5", ACTIVE_CANDIDATE_CONFIG is PHASE5_TREND_SCREEN_V1)
    print("FINGERPRINT", fp)
    print("ACTIVE_FINGERPRINT", active_fp)
    print("MATCH", fp == REQUIRED_FP == active_fp)
    print("LEGACY_FP", CandidateService.get_config_fingerprint(LEGACY_BATCH_A_POST_IMPORT_CONFIG))

    conn = sqlite3.connect(f"file:{ROOT / 'data' / 'swing_trading.db'}?mode=ro", uri=True)
    print("RUNS", conn.execute("SELECT COUNT(*) FROM candidate_evaluation_run").fetchone()[0])
    print("CRITERIA", conn.execute("SELECT COUNT(*) FROM candidate_criterion_result").fetchone()[0])
    print("RR", conn.execute("SELECT COUNT(*) FROM risk_reward_result").fetchone()[0])
    print("OHLCV", conn.execute("SELECT COUNT(*) FROM daily_ohlcv").fetchone()[0])
    print("SNAPS", conn.execute("SELECT COUNT(*) FROM fundamental_snapshot").fetchone()[0])
    print("FPS", conn.execute("SELECT config_fingerprint, COUNT(*) FROM candidate_evaluation_run GROUP BY 1").fetchall())
    print("MAX_ID", conn.execute("SELECT MAX(evaluation_id) FROM candidate_evaluation_run").fetchone()[0])
    q = """
    SELECT s.nse_symbol, COUNT(e.evaluation_id), MAX(e.evaluation_id),
           fs.entity_type, fs.source_line_item, fm.metric_value, fm.status
    FROM stock_master s
    LEFT JOIN candidate_evaluation_run e ON e.stock_id=s.stock_id
    LEFT JOIN fundamental_snapshot fs ON fs.stock_id=s.stock_id AND fs.is_superseded=0
    LEFT JOIN fundamental_metric fm ON fm.snapshot_id=fs.snapshot_id AND fm.metric_name='revenue'
    WHERE s.nse_symbol IN ({})
    GROUP BY s.nse_symbol
    """.format(",".join("?" * len(BATCH_B)))
    for row in conn.execute(q, BATCH_B):
        print("STOCK", row)
    conn.close()
    if fp != REQUIRED_FP:
        raise SystemExit("ABORT_FINGERPRINT")


if __name__ == "__main__":
    main()
