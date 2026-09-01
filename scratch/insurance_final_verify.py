"""Final read-only verification after the INSURANCE policy change."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(r"D:\Swing Trading")
DB = ROOT / "data" / "swing_trading.db"
sys.path.insert(0, str(ROOT / "backend"))

from app.services.candidate_config import ACTIVE_CANDIDATE_CONFIG, PHASE5_TREND_SCREEN_V1
from app.services.candidate_service import CandidateService
from app.services.fundamental_catalog import CANONICAL_SOURCE_LINE, ENTITY_TYPES, catalog_payload

print("=== CANONICAL MAPPINGS ===")
for entity, line in CANONICAL_SOURCE_LINE.items():
    print(f"  {entity:<10} {line}")
print("ENTITY_TYPES", ENTITY_TYPES)

payload = catalog_payload()
print("\ncatalog candidate_required_metrics:", payload["candidate_required_metrics"])
print("catalog revenue_unit:", payload["revenue_unit"])
print("catalog preferred_scope:", payload["revenue_policy"]["preferred_scope"])
print("insurance metric applicability:",
      {m["metric_name"]: m["insurance"] for m in payload["metrics"]})

print("\n=== PHASE 5 CONFIG ===")
print("active is PHASE5_TREND_SCREEN_V1:", ACTIVE_CANDIDATE_CONFIG is PHASE5_TREND_SCREEN_V1)
print("fingerprint:", CandidateService.get_config_fingerprint(ACTIVE_CANDIDATE_CONFIG))
print("criteria ids:", [c["id"] for c in ACTIVE_CANDIDATE_CONFIG["criteria"]])

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
q = conn.execute
counts = {t: q(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in (
    "daily_ohlcv", "stock_master", "fundamental_snapshot", "fundamental_metric",
    "candidate_evaluation_run", "candidate_criterion_result", "risk_reward_result",
    "broker_recommendation")}
print("\n=== PRODUCTION ===")
print(json.dumps(counts, indent=2))
print("synthetic_ohlcv:", q("SELECT COUNT(*) FROM daily_ohlcv WHERE open=100 AND high=105 "
                            "AND low=95 AND close=102 AND volume=1000").fetchone()[0])
print("entity_type distribution:", q(
    "SELECT entity_type, COUNT(*) FROM fundamental_snapshot GROUP BY entity_type").fetchall())
print("insurance snapshots:", q(
    "SELECT COUNT(*) FROM fundamental_snapshot WHERE entity_type='INSURANCE'").fetchone()[0])
print("HDFCLIFE snapshots:", q(
    "SELECT COUNT(*) FROM fundamental_snapshot f JOIN stock_master s ON s.stock_id=f.stock_id "
    "WHERE s.nse_symbol='HDFCLIFE'").fetchone()[0])
print("run config fingerprints:", q(
    "SELECT config_fingerprint, COUNT(*) FROM candidate_evaluation_run "
    "GROUP BY config_fingerprint").fetchall())
print("integrity_check:", q("PRAGMA integrity_check").fetchone()[0])
print("foreign_key_check:", len(q("PRAGMA foreign_key_check").fetchall()))
print("alembic_version:", q("SELECT * FROM alembic_version").fetchall())
conn.close()
