"""Candidate rule configurations.

Historical Batch A completeness-gate config is preserved as a constant.
Phase 5 is a new named configuration and must not overwrite that fingerprint.
"""
from typing import Any, Dict

LEGACY_BATCH_A_POST_IMPORT_CONFIG: Dict[str, Any] = {
    "name": "batch_a_post_import_evidence_gate",
    "criteria": [
        {"id": "SMA20", "type": "TECHNICAL", "operator": ">", "threshold": 0, "mandatory": True},
        {"id": "SMA50", "type": "TECHNICAL", "operator": ">", "threshold": 0, "mandatory": True},
        {"id": "SMA200", "type": "TECHNICAL", "operator": ">", "threshold": 0, "mandatory": True},
        {"id": "RSI14", "type": "TECHNICAL", "operator": ">=", "threshold": 0, "mandatory": True},
        {"id": "MACD", "type": "TECHNICAL", "operator": ">=", "threshold": -1000000, "mandatory": True},
        {"id": "ATR14", "type": "TECHNICAL", "operator": ">", "threshold": 0, "mandatory": True},
        {"id": "ROC20", "type": "TECHNICAL", "operator": ">=", "threshold": -1000000, "mandatory": True},
        {"id": "Liquidity20", "type": "TECHNICAL", "operator": ">", "threshold": 0, "mandatory": True},
        {"id": "revenue", "type": "FUNDAMENTAL", "operator": ">", "threshold": 0, "mandatory": True},
    ],
}

PHASE5_TREND_SCREEN_V1: Dict[str, Any] = {
    "name": "phase5_trend_screen_v1",
    "version": "phase5-v1",
    "label": "Passes the current Phase 5 trend screen. Not a guaranteed BUY.",
    "criteria": [
        {"id": "SMA20_known", "field": "SMA20", "type": "TECHNICAL", "operator": "KNOWN", "mandatory": True},
        {"id": "SMA50_known", "field": "SMA50", "type": "TECHNICAL", "operator": "KNOWN", "mandatory": True},
        {"id": "SMA200_known", "field": "SMA200", "type": "TECHNICAL", "operator": "KNOWN", "mandatory": True},
        {"id": "ATR14_known", "field": "ATR14", "type": "TECHNICAL", "operator": "KNOWN", "mandatory": True},
        {"id": "sma200_history", "field": "sessions", "type": "TECHNICAL", "operator": ">=", "threshold": 200, "mandatory": True},
        {"id": "revenue_known", "field": "revenue", "type": "FUNDAMENTAL", "operator": "KNOWN", "mandatory": True},
        {"id": "revenue_positive", "field": "revenue", "type": "FUNDAMENTAL", "operator": ">", "threshold": 0, "mandatory": True},
        {
            "id": "close_gt_sma50",
            "field": "latest_close",
            "type": "TECHNICAL",
            "operator": ">",
            "compare_to": "SMA50",
            "mandatory": True,
        },
        {
            "id": "sma50_gt_sma200",
            "field": "SMA50",
            "type": "TECHNICAL",
            "operator": ">",
            "compare_to": "SMA200",
            "mandatory": False,
        },
    ],
}

# Current live policy. Historical runs keep LEGACY_BATCH_A_POST_IMPORT_CONFIG snapshots.
ACTIVE_CANDIDATE_CONFIG: Dict[str, Any] = PHASE5_TREND_SCREEN_V1
