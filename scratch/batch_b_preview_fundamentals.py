"""Build Batch B genuine FY2025-26 intake JSON and run NON-PERSISTENT preview.

Does not call confirm. Does not write production tables.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(r"D:\Swing Trading")
sys.path.insert(0, str(ROOT / "backend"))

from app.database import SessionLocal
from app.models import (
    BrokerRecommendation,
    CandidateCriterionResult,
    CandidateEvaluationRun,
    DailyOhlcv,
    DataImportBatch,
    FundamentalSnapshot,
    RiskRewardResult,
    StockMaster,
)
from app.schemas.fundamental import FundamentalManualImport
from app.services.fundamental_import_service import FundamentalImportService

INTAKE = ROOT / "manual_inputs" / "fundamentals" / "batch_b_manual_intake.json"
PREVIEW = ROOT / "manual_inputs" / "fundamentals" / "batch_b_preview_results.json"

SOURCE_NAME = "NSE-filed audited annual financial results (board meeting outcome)"

ORDINARY_METRICS = [
    {"metric_name": "revenue", "metric_value": None, "status": "KNOWN"},
    {"metric_name": "ebitda", "metric_value": None, "status": "UNKNOWN"},
    {"metric_name": "inventory_turnover", "metric_value": None, "status": "UNKNOWN"},
    {"metric_name": "nim", "metric_value": None, "status": "NOT_APPLICABLE"},
    {"metric_name": "gnpa", "metric_value": None, "status": "NOT_APPLICABLE"},
    {"metric_name": "capital_adequacy", "metric_value": None, "status": "NOT_APPLICABLE"},
]
BANK_METRICS = [
    {"metric_name": "revenue", "metric_value": None, "status": "KNOWN"},
    {"metric_name": "ebitda", "metric_value": None, "status": "NOT_APPLICABLE"},
    {"metric_name": "inventory_turnover", "metric_value": None, "status": "NOT_APPLICABLE"},
    {"metric_name": "nim", "metric_value": None, "status": "UNKNOWN"},
    {"metric_name": "gnpa", "metric_value": None, "status": "UNKNOWN"},
    {"metric_name": "capital_adequacy", "metric_value": None, "status": "UNKNOWN"},
]
INSURANCE_METRICS = [
    {"metric_name": "revenue", "metric_value": None, "status": "KNOWN"},
    {"metric_name": "ebitda", "metric_value": None, "status": "NOT_APPLICABLE"},
    {"metric_name": "inventory_turnover", "metric_value": None, "status": "NOT_APPLICABLE"},
    {"metric_name": "nim", "metric_value": None, "status": "NOT_APPLICABLE"},
    {"metric_name": "gnpa", "metric_value": None, "status": "NOT_APPLICABLE"},
    {"metric_name": "capital_adequacy", "metric_value": None, "status": "NOT_APPLICABLE"},
]


def with_revenue(template, value: str):
    rows = []
    for item in template:
        row = dict(item)
        if row["metric_name"] == "revenue":
            row["metric_value"] = value
        rows.append(row)
    return rows


# Extracted from NSE-filed audited FY2025-26 annual results PDFs.
STOCKS = [
    {
        "nse_symbol": "CIPLA",
        "entity_type": "ORDINARY",
        "source_line_item": "Revenue from Operations",
        "statement_scope": "CONSOLIDATED",
        "original_reported_value": "28162.59",
        "original_reported_unit": "INR_CRORE",
        "normalized_inr_crore": "28162.59",
        "source_reference": "https://nsearchives.nseindia.com/corporate/CIPLA_13052026123600_SignedFinancialResults13052026Signed.pdf",
        "extraction_note": (
            "STATEMENT OF AUDITED CONSOLIDATED FINANCIAL RESULTS FOR THE QUARTER AND YEAR ENDED 31ST MARCH, 2026; "
            "(in Crores). Year ended 31-03-2026 Audited Total revenue from operations 28,162.59 "
            "(sale of products 27,711.69 + other operating revenue 450.90). Standalone 18,979.95 not used."
        ),
        "local_pdf": "manual_inputs/fundamentals/filings/pdfs/CIPLA_FY2025-26_annual.pdf",
        "metrics_template": ORDINARY_METRICS,
    },
    {
        "nse_symbol": "COALINDIA",
        "entity_type": "ORDINARY",
        "source_line_item": "Revenue from Operations",
        "statement_scope": "CONSOLIDATED",
        "original_reported_value": "168400.29",
        "original_reported_unit": "INR_CRORE",
        "normalized_inr_crore": "168400.29",
        "source_reference": "https://nsearchives.nseindia.com/corporate/COALINDIA_27042026202823_result_final.pdf",
        "extraction_note": (
            "STATEMENT OF CONSOLIDATED FINANCIAL RESULTS FOR THE QUARTER AND YEAR ENDED 31.03.2026; "
            "unit (in Crore). Year Ended 31.03.2026 Audited Revenue from Operations 1,68,400.29. "
            "Standalone page 21 1,577.29 not used."
        ),
        "local_pdf": "manual_inputs/fundamentals/filings/pdfs/COALINDIA_FY2025-26_annual.pdf",
        "metrics_template": ORDINARY_METRICS,
    },
    {
        "nse_symbol": "DRREDDY",
        "entity_type": "ORDINARY",
        "source_line_item": "Revenue from Operations",
        "statement_scope": "CONSOLIDATED",
        "original_reported_value": "337002",
        "original_reported_unit": "INR_MILLION",
        "normalized_inr_crore": "33700.2",
        "source_reference": "https://nsearchives.nseindia.com/corporate/DRREDDY_12052026163727_SEintimation_Outcome_of_BM_12052026_signed.pdf",
        "extraction_note": (
            "STATEMENT OF AUDITED CONSOLIDATED FINANCIAL RESULTS FOR THE QUARTER AND YEAR ENDED 31 MARCH 2026; "
            "All amounts in Indian Rupees millions. Year ended 31.03.2026 Audited Total revenue from operations 337,002. "
            "Normalized 337,002 million / 10 = 33,700.2 INR crore. Standalone 205,328 million not used."
        ),
        "local_pdf": "manual_inputs/fundamentals/filings/pdfs/DRREDDY_FY2025-26_annual.pdf",
        "metrics_template": ORDINARY_METRICS,
    },
    {
        "nse_symbol": "EICHERMOT",
        "entity_type": "ORDINARY",
        "source_line_item": "Revenue from Operations",
        "statement_scope": "CONSOLIDATED",
        "original_reported_value": "23407.56",
        "original_reported_unit": "INR_CRORE",
        "normalized_inr_crore": "23407.56",
        "source_reference": "https://nsearchives.nseindia.com/corporate/EICHERMOT_22052026164926_EMLOutcomeofBoardMeetingMay222026Signed.pdf",
        "extraction_note": (
            "STATEMENT OF CONSOLIDATED AUDITED FINANCIAL RESULTS FOR THE QUARTER AND YEAR ENDED MARCH 31, 2026; "
            "(Rs in Crores). Year ended 31.03.2026 Audited Total Revenue from operations 23,407.56. "
            "Standalone 22,699.73 not used."
        ),
        "local_pdf": "manual_inputs/fundamentals/filings/pdfs/EICHERMOT_FY2025-26_annual.pdf",
        "metrics_template": ORDINARY_METRICS,
    },
    {
        "nse_symbol": "ETERNAL",
        "entity_type": "ORDINARY",
        "source_line_item": "Revenue from Operations",
        "statement_scope": "CONSOLIDATED",
        "original_reported_value": "54364",
        "original_reported_unit": "INR_CRORE",
        "normalized_inr_crore": "54364",
        "source_reference": "https://nsearchives.nseindia.com/corporate/ZOMATO_28042026150911_Outcomesigned.pdf",
        "extraction_note": (
            "Eternal Limited (Formerly known as Zomato Limited) Statement of consolidated financial results "
            "for the quarter (unaudited) and year (audited) ended March 31, 2026; (INR crore). "
            "Year ended March 31, 2026 Audited Revenue from operations 54,364. Standalone  not used."
        ),
        "local_pdf": "manual_inputs/fundamentals/filings/pdfs/ETERNAL_FY2025-26_annual.pdf",
        "metrics_template": ORDINARY_METRICS,
    },
    {
        "nse_symbol": "GRASIM",
        "entity_type": "ORDINARY",
        "source_line_item": "Revenue from Operations",
        "statement_scope": "CONSOLIDATED",
        "original_reported_value": "175430.74",
        "original_reported_unit": "INR_CRORE",
        "normalized_inr_crore": "175430.74",
        "source_reference": "https://nsearchives.nseindia.com/corporate/GRASIM_20052026143701_Seintimationfinal.pdf",
        "extraction_note": (
            "AUDITED CONSOLIDATED FINANCIAL RESULTS FOR THREE MONTHS AND YEAR ENDED 31-03-2026; Rs in crore. "
            "Year Ended 31-03-2026 Audited Revenue from Operations 1,75,430.74. Standalone 41,039.48 not used."
        ),
        "local_pdf": "manual_inputs/fundamentals/filings/pdfs/GRASIM_FY2025-26_annual.pdf",
        "metrics_template": ORDINARY_METRICS,
    },
    {
        "nse_symbol": "HCLTECH",
        "entity_type": "ORDINARY",
        "source_line_item": "Revenue from Operations",
        "statement_scope": "CONSOLIDATED",
        "original_reported_value": "130144",
        "original_reported_unit": "INR_CRORE",
        "normalized_inr_crore": "130144",
        "source_reference": "https://nsearchives.nseindia.com/corporate/HCLTECH_21042026175820_FinancialResults.pdf",
        "extraction_note": (
            "Consolidated Statement of Financial Results of HCL Technologies Limited as per Ind AS; (in crores). "
            "Year ended 31 March 2026 Audited Revenue from operations 130,144. Standalone  not used as consolidated exists."
        ),
        "local_pdf": "manual_inputs/fundamentals/filings/pdfs/HCLTECH_FY2025-26_annual.pdf",
        "metrics_template": ORDINARY_METRICS,
    },
    {
        "nse_symbol": "HDFCBANK",
        "entity_type": "BANK",
        "source_line_item": "Total Income",
        "statement_scope": "CONSOLIDATED",
        "original_reported_value": "495462.81",
        "original_reported_unit": "INR_CRORE",
        "normalized_inr_crore": "495462.81",
        "source_reference": "https://nsearchives.nseindia.com/corporate/HDFCBANK_18042026144226_SEResultOutcome18042026.pdf",
        "extraction_note": (
            "HDFC BANK LIMITED CONSOLIDATED FINANCIAL RESULTS FOR THE QUARTER AND YEAR ENDED MARCH 31, 2026; "
            "(Rs in crore). Year ended 31.03.2026 Audited: Interest earned 348,615.15; Other income 146,847.66; "
            "Total income (1)+(2) 495,462.81. Interest Earned was not substituted. "
            "Standalone Total Income 370,054.65 not used."
        ),
        "local_pdf": "manual_inputs/fundamentals/filings/pdfs/HDFCBANK_FY2025-26_annual.pdf",
        "metrics_template": BANK_METRICS,
    },
    {
        "nse_symbol": "HDFCLIFE",
        "entity_type": "INSURANCE",
        "source_line_item": "Total Income (Policyholders' Account)",
        "statement_scope": "CONSOLIDATED",
        "original_reported_value": "9877038",
        "original_reported_unit": "INR_LAKH",
        "normalized_inr_crore": "98770.38",
        "source_reference": "https://nsearchives.nseindia.com/corporate/PRASAD_16042026163334_Board.pdf",
        "extraction_note": (
            "HDFC Life Insurance Company Limited Statement of Consolidated Audited Results for the Quarter and Year ended March 31, 2026; "
            "Rs in Lakh. POLICYHOLDERS' A/C Sr.No. 6 Total (2 to 5) year ended March 31, 2026 Audited 9,877,038. "
            "That is net premium 7,776,049 + income from investments (net) 2,018,835 + other income 34,874 + "
            "contribution from shareholders 47,280. Normalized 9,877,038 lakh / 100 = 98,770.38 INR crore. "
            "Shareholders' Account Profit after tax 191,232 lakh / Transfer from Policyholders' Account 120,114 lakh "
            "were recorded for exclusion and were NOT used. Gross/net premium were NOT used."
        ),
        "local_pdf": "manual_inputs/fundamentals/filings/pdfs/HDFCLIFE_FY2025-26_annual.pdf",
        "metrics_template": INSURANCE_METRICS,
        "hdfclife_exclusion": {
            "shareholders_profit_after_tax_lakh": "191232",
            "transfer_from_policyholders_lakh": "120114",
            "gross_premium_not_used": True,
            "net_premium_lakh_not_used_as_revenue": "7776049",
        },
    },
    {
        "nse_symbol": "HINDALCO",
        "entity_type": "ORDINARY",
        "source_line_item": "Revenue from Operations",
        "statement_scope": "CONSOLIDATED",
        "original_reported_value": "274944",
        "original_reported_unit": "INR_CRORE",
        "normalized_inr_crore": "274944",
        "source_reference": "https://nsearchives.nseindia.com/corporate/HINDALCOIND_22052026171757_BM_Outcome_2205_final_signed.pdf",
        "extraction_note": (
            "HINDALCO INDUSTRIES LIMITED Statement of Consolidated Audited Financial Results for the Year ended March 31, 2026; "
            "(in Crore). Year ended 31/03/2026 Audited Revenue from operations 274,944. Standalone 112,553 not used."
        ),
        "local_pdf": "manual_inputs/fundamentals/filings/pdfs/HINDALCO_FY2025-26_annual.pdf",
        "metrics_template": ORDINARY_METRICS,
    },
]


def counts(db) -> dict:
    syn = (
        db.query(DailyOhlcv)
        .filter(
            DailyOhlcv.open == 100,
            DailyOhlcv.high == 105,
            DailyOhlcv.low == 95,
            DailyOhlcv.close == 102,
            DailyOhlcv.volume == 1000,
        )
        .count()
    )
    return {
        "ohlcv": db.query(DailyOhlcv).count(),
        "synthetic_ohlcv": syn,
        "fundamental_snapshots": db.query(FundamentalSnapshot).count(),
        "fundamental_manual_batches": db.query(DataImportBatch)
        .filter(DataImportBatch.import_type == "FUNDAMENTAL_MANUAL")
        .count(),
        "candidate_runs": db.query(CandidateEvaluationRun).count(),
        "criterion_rows": db.query(CandidateCriterionResult).count(),
        "rr_rows": db.query(RiskRewardResult).count(),
        "broker_recommendations": db.query(BrokerRecommendation).count(),
    }


def main() -> None:
    db = SessionLocal()
    try:
        names = {s.nse_symbol: s.company_name for s in db.query(StockMaster).all()}
        stocks_out = []
        for spec in STOCKS:
            sym = spec["nse_symbol"]
            payload = {
                "nse_symbol": sym,
                "entity_type": spec["entity_type"],
                "as_of_date": "2026-03-31",
                "financial_period": "FY2025-26",
                "period_type": "ANNUAL",
                "source_name": SOURCE_NAME,
                "source_reference": spec["source_reference"],
                "statement_scope": spec["statement_scope"],
                "source_line_item": spec["source_line_item"],
                "original_unit": spec["original_reported_unit"],
                "metrics": with_revenue(spec["metrics_template"], spec["normalized_inr_crore"]),
            }
            row = {
                "nse_symbol": sym,
                "company_name": names.get(sym),
                "entity_type": spec["entity_type"],
                "source_line_item": spec["source_line_item"],
                "statement_scope": spec["statement_scope"],
                "original_reported_value": spec["original_reported_value"],
                "original_reported_unit": spec["original_reported_unit"],
                "normalized_inr_crore": spec["normalized_inr_crore"],
                "metric_status": "KNOWN",
                "extraction_note": spec["extraction_note"],
                "financial_period": "FY2025-26",
                "period_type": "ANNUAL",
                "as_of_date": "2026-03-31",
                "source_name": SOURCE_NAME,
                "source_reference": spec["source_reference"],
                "local_pdf": spec["local_pdf"],
                "ready_for_preview": True,
                "payload": payload,
            }
            if "hdfclife_exclusion" in spec:
                row["hdfclife_exclusion"] = spec["hdfclife_exclusion"]
            stocks_out.append(row)

        intake = {
            "do_not_confirm": True,
            "created_at": date.today().isoformat(),
            "purpose": "Batch B genuine FY2025-26 annual revenue intake. Preview only in this file. Do not confirm from this builder.",
            "canonical_revenue_policy": {
                "ORDINARY": "Revenue from Operations, CONSOLIDATED, stored INR_CRORE",
                "BANK": "Total Income, CONSOLIDATED, stored INR_CRORE",
                "NBFC": "Total Income, CONSOLIDATED, stored INR_CRORE",
                "INSURANCE": "Total Income (Policyholders' Account), CONSOLIDATED, stored INR_CRORE",
            },
            "reporting_basis": {
                "period_type": "ANNUAL",
                "financial_period": "FY2025-26",
                "as_of_date": "2026-03-31",
            },
            "stocks": stocks_out,
        }
        INTAKE.write_text(json.dumps(intake, indent=2), encoding="utf-8")

        before = counts(db)
        rows = []
        tally = {"ACCEPTED": 0, "DUPLICATE": 0, "CONFLICT": 0, "UNKNOWN": 0, "REJECTED": 0}
        for stock in stocks_out:
            payload = FundamentalManualImport(**stock["payload"])
            try:
                prev = FundamentalImportService.preview(db, payload)
                action = prev.get("action")
                errors = prev.get("errors")
            except ValueError as e:
                prev = {"persisted": False, "payload_sha256": None, "metrics": []}
                action = "REJECTED"
                errors = [str(e)]
            tally[action] = tally.get(action, 0) + 1
            rev = next((m for m in prev.get("metrics", []) if m["metric_name"] == "revenue"), {})
            rows.append(
                {
                    "symbol": stock["nse_symbol"],
                    "entity_type": stock["entity_type"],
                    "financial_period": stock["financial_period"],
                    "period_type": stock["period_type"],
                    "as_of_date": stock["as_of_date"],
                    "statement_scope": stock["statement_scope"],
                    "canonical_source_line": stock["source_line_item"],
                    "original_reported_value": stock["original_reported_value"],
                    "original_unit": stock["original_reported_unit"],
                    "normalized_inr_crore": stock["normalized_inr_crore"],
                    "preview_revenue_value": rev.get("metric_value"),
                    "preview_revenue_status": rev.get("status"),
                    "source_name": stock["source_name"],
                    "source_reference": stock["source_reference"],
                    "payload_sha256": prev.get("payload_sha256"),
                    "preview_status": action,
                    "persisted": prev.get("persisted"),
                    "errors": errors,
                }
            )
            print(
                stock["nse_symbol"],
                action,
                stock["normalized_inr_crore"],
                (prev.get("payload_sha256") or "")[:16],
                errors or "",
            )

        after = counts(db)
        report = {
            "counts": tally,
            "before": before,
            "after": after,
            "unchanged": before == after,
            "results": rows,
        }
        PREVIEW.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(json.dumps({"counts": tally, "before": before, "after": after, "unchanged": before == after}, indent=2))
        if before != after:
            raise SystemExit("PRODUCTION WRITE DETECTED DURING PREVIEW")
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
