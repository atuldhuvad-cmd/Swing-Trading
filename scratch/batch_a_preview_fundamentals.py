"""Populate Batch A intake from verified NSE PDFs and run non-persistent preview only."""
from __future__ import annotations

import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, r"D:\Swing Trading\backend")

from app.database import SessionLocal
from app.models import FundamentalSnapshot, DataImportBatch, CandidateEvaluationRun
from app.schemas.fundamental import FundamentalManualImport, FundamentalMetricIn
from app.services.fundamental_import_service import FundamentalImportService

ROOT = Path(r"D:\Swing Trading")
INTAKE = ROOT / "manual_inputs" / "fundamentals" / "batch_a_manual_intake.json"
PREVIEW_OUT = ROOT / "manual_inputs" / "fundamentals" / "batch_a_preview_results.json"

PDF = {
    "ADANIENT": "https://nsearchives.nseindia.com/corporate/ADANIENT_30042026153306_AELBMOutcome30042026.pdf",
    "ADANIPORTS": "https://nsearchives.nseindia.com/corporate/rkbhagia_30042026134205_OutcomeofBoardMeeting.pdf",
    "APOLLOHOSP": "https://nsearchives.nseindia.com/corporate/APOLLOHOSP_20052026175246_SE_outcome_Board_Meeting.pdf",
    "ASIANPAINT": "https://nsearchives.nseindia.com/corporate/ASIANPAINT_29052026140521_SEIntimationoutcomeFY26.pdf",
    "AXISBANK": "https://nsearchives.nseindia.com/corporate/AXISBANK1_25042026125818_AFRQ4FY26.pdf",
    "BAJAJ-AUTO": "https://nsearchives.nseindia.com/corporate/lkwalimbe_bajajauto_co_in_06052026182412_Outcome_of_Board_Meeting.pdf",
    "BAJAJFINSV": "https://nsearchives.nseindia.com/corporate/walimbelk_30042026141401_BFSBMOUTCOMEFINAL30APRIL2026_1.pdf",
    "BAJFINANCE": "https://nsearchives.nseindia.com/corporate/BAJFINANCE_29042026163247_BSENSEOUTCOME.pdf",
    "BEL": "https://nsearchives.nseindia.com/corporate/BEL_19052026151725_Letter_signed.pdf",
    "BHARTIARTL": "https://nsearchives.nseindia.com/corporate/BHARTIARTL_13052026163920_FR_Final.pdf",
}

SOURCE_NAME = "NSE-filed audited annual financial results (board meeting outcome)"


def ordinary_metrics(revenue: str | None, known: bool):
    return [
        FundamentalMetricIn(
            metric_name="revenue",
            metric_value=revenue if known else None,
            status="KNOWN" if known else "UNKNOWN",
        ),
        FundamentalMetricIn(metric_name="ebitda", status="UNKNOWN"),
        FundamentalMetricIn(metric_name="inventory_turnover", status="UNKNOWN"),
        FundamentalMetricIn(metric_name="nim", status="NOT_APPLICABLE"),
        FundamentalMetricIn(metric_name="gnpa", status="NOT_APPLICABLE"),
        FundamentalMetricIn(metric_name="capital_adequacy", status="NOT_APPLICABLE"),
    ]


def bank_nbfc_metrics(revenue: str | None, known: bool):
    return [
        FundamentalMetricIn(
            metric_name="revenue",
            metric_value=revenue if known else None,
            status="KNOWN" if known else "UNKNOWN",
        ),
        FundamentalMetricIn(metric_name="ebitda", status="NOT_APPLICABLE"),
        FundamentalMetricIn(metric_name="inventory_turnover", status="NOT_APPLICABLE"),
        FundamentalMetricIn(metric_name="nim", status="UNKNOWN"),
        FundamentalMetricIn(metric_name="gnpa", status="UNKNOWN"),
        FundamentalMetricIn(metric_name="capital_adequacy", status="UNKNOWN"),
    ]


# Verified from NSE PDFs. original_value is as printed; normalized is INR crore Decimal string.
STOCKS = [
    {
        "nse_symbol": "ADANIENT",
        "company_name": "Adani Enterprises Ltd.",
        "entity_type": "ORDINARY",
        "source_line_item": "Revenue from Operations",
        "statement_scope": "CONSOLIDATED",
        "original_reported_value": "100468.61",
        "original_reported_unit": "INR_CRORE",
        "normalized_inr_crore": "100468.61",
        "metric_status": "KNOWN",
        "extraction_note": "Consolidated P&L year ended 31-03-2026; matches segment net revenue from operations.",
    },
    {
        "nse_symbol": "ADANIPORTS",
        "company_name": "Adani Ports and Special Economic Zone Ltd.",
        "entity_type": "ORDINARY",
        "source_line_item": "Revenue from Operations",
        "statement_scope": "CONSOLIDATED",
        "original_reported_value": "38735.77",
        "original_reported_unit": "INR_CRORE",
        "normalized_inr_crore": "38735.77",
        "metric_status": "KNOWN",
        "extraction_note": "CONSOLIDATED FINANCIAL RESULTS year ended March 31, 2026 (tin crore).",
    },
    {
        "nse_symbol": "APOLLOHOSP",
        "company_name": "Apollo Hospitals Enterprise Ltd.",
        "entity_type": "ORDINARY",
        "source_line_item": "Revenue from Operations",
        "statement_scope": "CONSOLIDATED",
        "original_reported_value": "252285",
        "original_reported_unit": "INR_MILLION",
        "normalized_inr_crore": "25228.50",
        "metric_status": "KNOWN",
        "extraction_note": "Consolidated P&L year ended 31/03/2026 stated in Rs. million; 252285 million = 25228.50 crore.",
    },
    {
        "nse_symbol": "ASIANPAINT",
        "company_name": "Asian Paints Ltd.",
        "entity_type": "ORDINARY",
        "source_line_item": "Revenue from Operations",
        "statement_scope": "CONSOLIDATED",
        "original_reported_value": "35583.54",
        "original_reported_unit": "INR_CRORE",
        "normalized_inr_crore": "35583.54",
        "metric_status": "KNOWN",
        "extraction_note": "Consolidated year-ended column block maps to Revenue from operations 35,583.54 (t in Crores).",
    },
    {
        "nse_symbol": "AXISBANK",
        "company_name": "Axis Bank Ltd.",
        "entity_type": "BANK",
        "source_line_item": "Total Income",
        "statement_scope": "CONSOLIDATED",
        "original_reported_value": "162211.95",
        "original_reported_unit": "INR_CRORE",
        "normalized_inr_crore": "162211.95",
        "metric_status": "KNOWN",
        "extraction_note": "AUDITED CONSOLIDATED FINANCIAL RESULTS year ended 31.03.2026 TOTAL INCOME (1+2); 132538.24 interest earned + 29673.71 other income.",
    },
    {
        "nse_symbol": "BAJAJ-AUTO",
        "company_name": "Bajaj Auto Ltd.",
        "entity_type": "ORDINARY",
        "source_line_item": "Revenue from Operations",
        "statement_scope": "CONSOLIDATED",
        "original_reported_value": "62905.00",
        "original_reported_unit": "INR_CRORE",
        "normalized_inr_crore": "62905.00",
        "metric_status": "KNOWN",
        "extraction_note": "Consolidated audited results: Total revenue from operations year ended 31.03.2026 (f In Crore).",
    },
    {
        "nse_symbol": "BAJAJFINSV",
        "company_name": "Bajaj Finserv Ltd.",
        "entity_type": "ORDINARY",
        "source_line_item": "Revenue from Operations",
        "statement_scope": "CONSOLIDATED",
        "original_reported_value": "150501.77",
        "original_reported_unit": "INR_CRORE",
        "normalized_inr_crore": "150501.77",
        "metric_status": "KNOWN",
        "extraction_note": "Consolidated P&L Total revenue from operations year ended 31.03.2026 (Indian grouping 1,50,501.77).",
    },
    {
        "nse_symbol": "BAJFINANCE",
        "company_name": "Bajaj Finance Ltd.",
        "entity_type": "NBFC",
        "source_line_item": "Total Income",
        "statement_scope": "CONSOLIDATED",
        "original_reported_value": "81989.50",
        "original_reported_unit": "INR_CRORE",
        "normalized_inr_crore": "81989.50",
        "metric_status": "KNOWN",
        "extraction_note": "Consolidated P&L Total income year ended 31.03.2026 (z in crore); 81982.38 operations + 7.12 other income.",
    },
    {
        "nse_symbol": "BEL",
        "company_name": "Bharat Electronics Ltd.",
        "entity_type": "ORDINARY",
        "source_line_item": "Revenue from Operations",
        "statement_scope": "CONSOLIDATED",
        "original_reported_value": None,
        "original_reported_unit": None,
        "normalized_inr_crore": None,
        "metric_status": "UNKNOWN",
        "extraction_note": "NSE PDF is a scanned letter; P&L table not reliably extractable. Press-release figure in same PDF was not used.",
    },
    {
        "nse_symbol": "BHARTIARTL",
        "company_name": "Bharti Airtel Ltd.",
        "entity_type": "ORDINARY",
        "source_line_item": "Revenue from Operations",
        "statement_scope": "CONSOLIDATED",
        "original_reported_value": "2109728",
        "original_reported_unit": "INR_MILLION",
        "normalized_inr_crore": "210972.80",
        "metric_status": "KNOWN",
        "extraction_note": "Audited consolidated results year ended 31 Mar 2026 in Rs. million; 2109728 million = 210972.80 crore.",
    },
]


def metrics_for(stock: dict):
    known = stock["metric_status"] == "KNOWN"
    val = stock["normalized_inr_crore"]
    if stock["entity_type"] in ("BANK", "NBFC"):
        return bank_nbfc_metrics(val, known)
    return ordinary_metrics(val, known)


def payload_for(stock: dict) -> FundamentalManualImport:
    known = stock["metric_status"] == "KNOWN"
    return FundamentalManualImport(
        nse_symbol=stock["nse_symbol"],
        entity_type=stock["entity_type"],
        as_of_date=date(2026, 3, 31),
        financial_period="FY2025-26",
        period_type="ANNUAL",
        source_name=SOURCE_NAME if known else "PENDING_PRIMARY_P_AND_L_LINE",
        source_reference=PDF[stock["nse_symbol"]],
        metrics=metrics_for(stock),
    )


def main() -> None:
    intake = {
        "do_not_confirm": True,
        "created_at": "2026-08-14",
        "purpose": "Batch A genuine FY2025-26 annual revenue intake. Preview only. Do not confirm.",
        "canonical_revenue_policy": {
            "ORDINARY": "Revenue from Operations, CONSOLIDATED, INR_CRORE",
            "BANK": "Total Income, CONSOLIDATED, INR_CRORE",
            "NBFC": "Total Income, CONSOLIDATED, INR_CRORE",
            "candidate_rule_unchanged": "revenue > 0",
        },
        "reporting_basis": {
            "period_type": "ANNUAL",
            "financial_period": "FY2025-26",
            "as_of_date": "2026-03-31",
        },
        "stocks": [],
    }
    for stock in STOCKS:
        p = payload_for(stock)
        intake["stocks"].append(
            {
                **{k: stock[k] for k in stock},
                "financial_period": "FY2025-26",
                "period_type": "ANNUAL",
                "as_of_date": "2026-03-31",
                "source_name": p.source_name,
                "source_reference": p.source_reference,
                "ready_for_preview": stock["metric_status"] == "KNOWN",
                "payload": json.loads(p.model_dump_json()),
            }
        )
    INTAKE.write_text(json.dumps(intake, indent=2), encoding="utf-8")

    db = SessionLocal()
    results = []
    try:
        before = {
            "snapshots": db.query(FundamentalSnapshot).count(),
            "fund_batches": db.query(DataImportBatch)
            .filter(DataImportBatch.import_type == "FUNDAMENTAL_MANUAL")
            .count(),
            "evals": db.query(CandidateEvaluationRun).count(),
        }
        for stock in STOCKS:
            if stock["metric_status"] != "KNOWN":
                results.append(
                    {
                        "symbol": stock["nse_symbol"],
                        "preview_status": "UNKNOWN",
                        "reason": stock["extraction_note"],
                    }
                )
                continue
            payload = payload_for(stock)
            prev = FundamentalImportService.preview(db, payload)
            results.append(
                {
                    "symbol": stock["nse_symbol"],
                    "entity_type": stock["entity_type"],
                    "period": "FY2025-26",
                    "scope": stock["statement_scope"],
                    "canonical_source_line": stock["source_line_item"],
                    "original_reported_value": stock["original_reported_value"],
                    "original_unit": stock["original_reported_unit"],
                    "normalized_inr_crore": stock["normalized_inr_crore"],
                    "source": PDF[stock["nse_symbol"]],
                    "preview_status": prev.get("action"),
                    "persisted": prev.get("persisted"),
                    "message": prev.get("message"),
                    "errors": prev.get("errors"),
                }
            )
        after = {
            "snapshots": db.query(FundamentalSnapshot).count(),
            "fund_batches": db.query(DataImportBatch)
            .filter(DataImportBatch.import_type == "FUNDAMENTAL_MANUAL")
            .count(),
            "evals": db.query(CandidateEvaluationRun).count(),
        }
        PREVIEW_OUT.write_text(
            json.dumps({"before": before, "after": after, "results": results}, indent=2, default=str),
            encoding="utf-8",
        )
        print(json.dumps({"before": before, "after": after, "results": results}, indent=2, default=str))
        if after != before:
            raise SystemExit("PRODUCTION CHANGED DURING PREVIEW")
    finally:
        db.close()


if __name__ == "__main__":
    main()
