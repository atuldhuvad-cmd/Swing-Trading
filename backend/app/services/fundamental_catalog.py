"""Canonical fundamental metrics for swing-candidate evaluation.

The live candidate rule currently requires only `revenue` as a mandatory
fundamental. Other catalog metrics are captured for evidence completeness
and entity-appropriate handling. Missing required metrics stay UNKNOWN.
"""
from typing import Dict, List

ENTITY_TYPES = ("ORDINARY", "BANK", "NBFC", "INSURANCE")
STATUSES = ("KNOWN", "UNKNOWN", "NOT_APPLICABLE", "STALE", "UNSUPPORTED")
PERIOD_TYPES = ("ANNUAL", "QUARTERLY", "HALF_YEARLY", "TTM")
STATEMENT_SCOPES = ("CONSOLIDATED", "STANDALONE")
REVENUE_UNIT = "INR_CRORE"
ORIGINAL_UNITS = ("INR_CRORE", "INR_MILLION", "INR_LAKH")

# Life insurers do not report "Revenue from Operations", and the bare label
# "Total Income" is ambiguous for them: the exchange-filed life insurance format
# carries one Total Income under the Policyholders' Account and a second,
# narrower one under the Shareholders' Account. The Policyholders' line is the
# prescribed total of the income block and is therefore qualified explicitly.
INSURANCE_REVENUE_LINE = "Total Income (Policyholders' Account)"
CANONICAL_SOURCE_LINE = {
    "ORDINARY": "Revenue from Operations",
    "BANK": "Total Income",
    "NBFC": "Total Income",
    "INSURANCE": INSURANCE_REVENUE_LINE,
}

# Canonical revenue mapping. Does not change the candidate rule (revenue > 0).
REVENUE_POLICY = {
    "metric_name": "revenue",
    "unit": REVENUE_UNIT,
    "preferred_scope": "CONSOLIDATED",
    "standalone_allowed_only_if_consolidated_absent": True,
    "ordinary": {
        "source_line_item": "Revenue from Operations",
        "do_not_substitute": ["Sales", "Total Income", "Other Income"],
    },
    "bank": {
        "source_line_item": "Total Income",
        "do_not_substitute": ["Interest Earned", "Interest Income", "Revenue from Operations"],
    },
    "nbfc": {
        "source_line_item": "Total Income",
        "do_not_substitute": ["Interest Income", "Revenue from Operations"],
    },
    "insurance": {
        "source_line_item": INSURANCE_REVENUE_LINE,
        "authority": (
            "IRDAI (Preparation of Financial Statements and Auditor's Report of "
            "Insurance Companies) Regulations, 2002 Form A-RA Revenue Account "
            "[Policyholders' Account] TOTAL (A); presented as 'Total Income' in the "
            "Policyholders' Accounts income block of the exchange-filed format for "
            "financial results by life insurance companies."
        ),
        "do_not_substitute": [
            "Revenue from Operations",
            "Total Income",
            "Total Income (Shareholders' Account)",
            "Gross premium income",
            "Net premium income",
            "Premium Income",
            "Income from investments (Net)",
        ],
    },
}

# required_by_candidate_rule is the actual Batch A / candidate engine gate.
METRICS: List[Dict[str, object]] = [
    {
        "metric_name": "revenue",
        "label": "Revenue from operations (ordinary) / Total income (bank, NBFC)",
        "unit": REVENUE_UNIT,
        "required_by_candidate_rule": True,
        "ordinary": True,
        "bank": True,
        "nbfc": True,
        "insurance": True,
        "default_if_omitted": "UNKNOWN",
        "missing_behavior": "UNKNOWN → candidate INSUFFICIENT_DATA when mandatory",
    },
    {
        "metric_name": "ebitda",
        "label": "EBITDA",
        "required_by_candidate_rule": False,
        "ordinary": True,
        "bank": False,
        "nbfc": False,
        "insurance": False,
        "default_if_omitted": None,
        "missing_behavior": "UNKNOWN for ordinary if omitted; NOT_APPLICABLE for bank/NBFC/insurance",
    },
    {
        "metric_name": "inventory_turnover",
        "label": "Inventory turnover",
        "required_by_candidate_rule": False,
        "ordinary": True,
        "bank": False,
        "nbfc": False,
        "insurance": False,
        "default_if_omitted": None,
        "missing_behavior": "UNKNOWN for ordinary if omitted; NOT_APPLICABLE for bank/NBFC/insurance",
    },
    {
        "metric_name": "nim",
        "label": "Net interest margin",
        "required_by_candidate_rule": False,
        "ordinary": False,
        "bank": True,
        "nbfc": True,
        "insurance": False,
        "default_if_omitted": None,
        "missing_behavior": "NOT_APPLICABLE for ordinary/insurance; UNKNOWN for bank/NBFC if omitted",
    },
    {
        "metric_name": "gnpa",
        "label": "Gross NPA %",
        "required_by_candidate_rule": False,
        "ordinary": False,
        "bank": True,
        "nbfc": True,
        "insurance": False,
        "default_if_omitted": None,
        "missing_behavior": "NOT_APPLICABLE for ordinary/insurance; UNKNOWN for bank/NBFC if omitted",
    },
    {
        "metric_name": "capital_adequacy",
        "label": "Capital adequacy ratio",
        "required_by_candidate_rule": False,
        "ordinary": False,
        "bank": True,
        "nbfc": True,
        # Insurers report an IRDAI solvency ratio, not a Basel capital adequacy
        # ratio. No insurance-specific quality metric is introduced here.
        "insurance": False,
        "default_if_omitted": None,
        "missing_behavior": "NOT_APPLICABLE for ordinary/insurance; UNKNOWN for bank/NBFC if omitted",
    },
]

CANDIDATE_REQUIRED_METRICS = [m["metric_name"] for m in METRICS if m["required_by_candidate_rule"]]


ENTITY_METRIC_KEY = {
    "ORDINARY": "ordinary",
    "BANK": "bank",
    "NBFC": "nbfc",
    "INSURANCE": "insurance",
}


def applicability(metric: Dict[str, object], entity_type: str) -> bool:
    return bool(metric[ENTITY_METRIC_KEY[entity_type]])


def default_status(metric: Dict[str, object], entity_type: str) -> str:
    if applicability(metric, entity_type):
        return "UNKNOWN"
    return "NOT_APPLICABLE"


def catalog_payload() -> Dict[str, object]:
    return {
        "candidate_required_metrics": CANDIDATE_REQUIRED_METRICS,
        "entity_types": list(ENTITY_TYPES),
        "entity_metric_key": dict(ENTITY_METRIC_KEY),
        "statuses": list(STATUSES),
        "period_types": list(PERIOD_TYPES),
        "statement_scopes": list(STATEMENT_SCOPES),
        "original_units": list(ORIGINAL_UNITS),
        "canonical_source_line": dict(CANONICAL_SOURCE_LINE),
        "revenue_unit": REVENUE_UNIT,
        "revenue_policy": REVENUE_POLICY,
        "metrics": METRICS,
    }
