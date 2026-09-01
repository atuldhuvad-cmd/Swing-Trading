"""Preview all Batch A intake payloads. Does not confirm. Does not rewrite intake."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, r"D:\Swing Trading\backend")

from app.database import SessionLocal
from app.models import CandidateEvaluationRun, DailyOhlcv, DataImportBatch, FundamentalSnapshot
from app.schemas.fundamental import FundamentalManualImport
from app.services.fundamental_import_service import FundamentalImportService

INTAKE = Path(r"D:\Swing Trading\manual_inputs\fundamentals\batch_a_manual_intake.json")
OUT = Path(r"D:\Swing Trading\manual_inputs\fundamentals\batch_a_preview_results.json")

LINE = {
    "ORDINARY": "Revenue from Operations",
    "BANK": "Total Income",
    "NBFC": "Total Income",
}


def main() -> None:
    intake = json.loads(INTAKE.read_text(encoding="utf-8"))
    db = SessionLocal()
    rows = []
    try:
        before = {
            "snapshots": db.query(FundamentalSnapshot).count(),
            "fund_batches": db.query(DataImportBatch)
            .filter(DataImportBatch.import_type == "FUNDAMENTAL_MANUAL")
            .count(),
            "evals": db.query(CandidateEvaluationRun).count(),
            "ohlcv": db.query(DailyOhlcv).count(),
        }
        counts = {"ACCEPTED": 0, "DUPLICATE": 0, "CONFLICT": 0, "UNKNOWN": 0, "REJECTED": 0}
        for stock in intake["stocks"]:
            payload = FundamentalManualImport(**stock["payload"])
            prev = FundamentalImportService.preview(db, payload)
            action = prev.get("action")
            if stock.get("metric_status") != "KNOWN":
                action = "UNKNOWN"
            counts[action] = counts.get(action, 0) + 1
            rev = next(m for m in prev["metrics"] if m["metric_name"] == "revenue")
            rows.append(
                {
                    "symbol": stock["nse_symbol"],
                    "entity_type": payload.entity_type,
                    "financial_period": payload.financial_period,
                    "period_type": payload.period_type,
                    "as_of_date": str(payload.as_of_date),
                    "statement_scope": stock.get("statement_scope"),
                    "canonical_source_line": stock.get("source_line_item") or LINE[payload.entity_type],
                    "original_reported_value": stock.get("original_reported_value"),
                    "original_unit": stock.get("original_reported_unit"),
                    "normalized_inr_crore": stock.get("normalized_inr_crore"),
                    "preview_revenue_value": rev.get("metric_value"),
                    "preview_revenue_status": rev.get("status"),
                    "source_name": payload.source_name,
                    "source_reference": payload.source_reference,
                    "payload_sha256": prev.get("payload_sha256"),
                    "preview_status": action,
                    "persisted": prev.get("persisted"),
                    "errors": prev.get("errors"),
                }
            )
        after = {
            "snapshots": db.query(FundamentalSnapshot).count(),
            "fund_batches": db.query(DataImportBatch)
            .filter(DataImportBatch.import_type == "FUNDAMENTAL_MANUAL")
            .count(),
            "evals": db.query(CandidateEvaluationRun).count(),
            "ohlcv": db.query(DailyOhlcv).count(),
        }
        report = {"counts": counts, "before": before, "after": after, "results": rows}
        OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        if after != before:
            raise SystemExit("PRODUCTION CHANGED DURING PREVIEW")
    finally:
        db.close()


if __name__ == "__main__":
    main()
