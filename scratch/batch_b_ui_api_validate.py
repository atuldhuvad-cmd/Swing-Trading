"""Read-only Evidence API validation against latest Batch B Phase 5 results."""
from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

BASE = "http://127.0.0.1:8000"
DB = Path(r"D:\Swing Trading\data\swing_trading.db")
PHASE5_FP = "146408d7d5de3ce55acd5465d2c788acca9d8e1875c21e1af470151a3f0f97fe"
BATCH_B = {
    "CIPLA": "FINAL_CANDIDATE",
    "COALINDIA": "REJECTED",
    "DRREDDY": "REJECTED",
    "EICHERMOT": "FINAL_CANDIDATE",
    "ETERNAL": "FINAL_CANDIDATE",
    "GRASIM": "FINAL_CANDIDATE",
    "HCLTECH": "WATCH",
    "HDFCBANK": "REJECTED",
    "HDFCLIFE": "REJECTED",
    "HINDALCO": "FINAL_CANDIDATE",
}
EXPECTED_EXAMPLES = {
    "CIPLA": {"close": "1458.8", "sma50": "1429.57", "sma200": "1402.83"},
    "COALINDIA": {"close": "410.5", "sma50": "433.72"},
    "HCLTECH": {"close": "1370.0", "sma50": "1208.39", "sma200": "1409.02"},
    "HDFCLIFE": {"close": "538.05", "sma50": "562.8", "sma200": "659.74"},
}
RR_STORED = {
    "CIPLA": "0.4639",
    "COALINDIA": "2.0070",
    "DRREDDY": "0.4162",
    "GRASIM": "0.9558",
    "HDFCBANK": "5.3229",
    "HDFCLIFE": "2.8142",
    "HINDALCO": "0.8121",
}
RR_NA = {"EICHERMOT", "ETERNAL", "HCLTECH"}
INSURANCE_LINE = "Total Income (Policyholders' Account)"
defects: list[str] = []


def get(path: str):
    with urlopen(BASE + path, timeout=30) as resp:
        return resp.status, json.loads(resp.read().decode())


def almost(a, b, places=2) -> bool:
    if a is None or b is None:
        return False
    return abs(Decimal(str(a)) - Decimal(str(b))) < Decimal("0.02")


def prefix(a, expected: str) -> bool:
    if a is None:
        return False
    return str(a).startswith(expected.rstrip("0").rstrip(".") if "." in expected else expected) or str(a).startswith(expected)


c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
db_latest = dict(
    c.execute(
        """
        SELECT s.nse_symbol, MAX(e.evaluation_id)
        FROM stock_master s
        JOIN candidate_evaluation_run e ON e.stock_id = s.stock_id
        WHERE s.nse_symbol IN ({})
        GROUP BY s.nse_symbol
        """.format(",".join("?" * len(BATCH_B))),
        tuple(BATCH_B),
    ).fetchall()
)
print("db_latest_eval_ids", db_latest)

status, health = get("/health")
print("HEALTH", status, health)
if health.get("status") != "ok":
    defects.append(f"health status {health.get('status')}")
if str(health.get("foreign_keys")) not in ("1", "True", "true"):
    defects.append(f"foreign_keys {health.get('foreign_keys')}")

status, listed = get("/api/evidence/candidates")
items = listed.get("items") or []
by_sym = {row["nse_symbol"]: row for row in items}
print("candidates_count", len(items))
counts: dict[str, int] = {}
for row in items:
    counts[row["status"]] = counts.get(row["status"], 0) + 1
print("universe_counts", counts)

batch_counts: dict[str, int] = {}
for sym, expected in BATCH_B.items():
    row = by_sym.get(sym)
    if not row:
        defects.append(f"{sym} missing from candidates list")
        continue
    batch_counts[row["status"]] = batch_counts.get(row["status"], 0) + 1
    if row["status"] != expected:
        defects.append(f"{sym} list status {row['status']} != {expected}")
    if row["evaluation_id"] != db_latest.get(sym):
        defects.append(f"{sym} list eval {row['evaluation_id']} != db latest {db_latest.get(sym)}")
    if row.get("config_fingerprint") != PHASE5_FP:
        defects.append(f"{sym} fingerprint {row.get('config_fingerprint')}")
print("batch_b_list_counts", batch_counts)
if batch_counts.get("FINAL_CANDIDATE") != 5:
    defects.append(f"list FINAL {batch_counts.get('FINAL_CANDIDATE')}")
if batch_counts.get("WATCH") != 1:
    defects.append(f"list WATCH {batch_counts.get('WATCH')}")
if batch_counts.get("REJECTED") != 4:
    defects.append(f"list REJECTED {batch_counts.get('REJECTED')}")
if batch_counts.get("INSUFFICIENT_DATA", 0) != 0:
    defects.append(f"list INSUFFICIENT {batch_counts.get('INSUFFICIENT_DATA')}")

for sym, expected in BATCH_B.items():
    row = by_sym.get(sym)
    if not row:
        continue
    stock_id = row["stock_id"]
    st, body = get(f"/api/evidence/stocks/{stock_id}")
    cand = body.get("candidate") or {}
    tech = body.get("technical") or {}
    inds = tech.get("indicators") or {}
    print(
        f"DETAIL {sym} eval={cand.get('evaluation_id')} class={cand.get('classification')} "
        f"close={tech.get('latest_close')} sma50={inds.get('SMA50')} sma200={inds.get('SMA200')} "
        f"entity={body.get('fundamental_entity_type')} line={(body.get('fundamental_provenance') or {}).get('source_line_item')} "
        f"rr={(body.get('risk_reward') or {}).get('rr_ratio')}"
    )
    if cand.get("evaluation_id") != db_latest.get(sym):
        defects.append(f"{sym} detail eval {cand.get('evaluation_id')} != db {db_latest.get(sym)}")
    if cand.get("classification") != expected:
        defects.append(f"{sym} detail class {cand.get('classification')} != {expected}")
    if cand.get("config_fingerprint") != PHASE5_FP:
        defects.append(f"{sym} detail fingerprint")
    if not cand.get("decisive_reason"):
        defects.append(f"{sym} missing decisive_reason")
    if not body.get("criteria"):
        defects.append(f"{sym} missing criteria")
    if not body.get("close_gt_sma50"):
        defects.append(f"{sym} missing close_gt_sma50")
    if not body.get("sma50_gt_sma200"):
        defects.append(f"{sym} missing sma50_gt_sma200")
    revenue = next((m for m in (body.get("fundamentals") or []) if m.get("metric_name") == "revenue"), None)
    if not revenue:
        defects.append(f"{sym} missing revenue metric")
    else:
        if revenue.get("status") != "KNOWN":
            defects.append(f"{sym} revenue status {revenue.get('status')}")
        if revenue.get("metric_value") is None:
            defects.append(f"{sym} revenue value missing")
    ex = EXPECTED_EXAMPLES.get(sym)
    if ex:
        if not almost(tech.get("latest_close"), ex["close"]):
            defects.append(f"{sym} close {tech.get('latest_close')} != {ex['close']}")
        if not almost(inds.get("SMA50"), ex["sma50"]):
            defects.append(f"{sym} sma50 {inds.get('SMA50')} != {ex['sma50']}")
        if "sma200" in ex and not almost(inds.get("SMA200"), ex["sma200"]):
            defects.append(f"{sym} sma200 {inds.get('SMA200')} != {ex['sma200']}")
    rr = body.get("risk_reward")
    if sym in RR_NA:
        if rr and rr.get("rr_ratio"):
            defects.append(f"{sym} fabricated RR {rr.get('rr_ratio')}")
        if row.get("rr_available"):
            defects.append(f"{sym} list rr_available true")
    if sym in RR_STORED:
        if not rr or not prefix(rr.get("rr_ratio"), RR_STORED[sym][:4]):
            defects.append(f"{sym} RR {None if not rr else rr.get('rr_ratio')} != {RR_STORED[sym]}")
        if not row.get("rr_available"):
            defects.append(f"{sym} list rr_available false")

st, hdfc = get(f"/api/evidence/stocks/{by_sym['HDFCLIFE']['stock_id']}")
rev = next((m for m in hdfc.get("fundamentals") or [] if m.get("metric_name") == "revenue"), None)
prov = hdfc.get("fundamental_provenance") or {}
print("HDFCLIFE_ENTITY", hdfc.get("fundamental_entity_type"))
print("HDFCLIFE_REV", rev)
print("HDFCLIFE_PROV", prov)
if hdfc.get("fundamental_entity_type") != "INSURANCE":
    defects.append(f"HDFCLIFE entity {hdfc.get('fundamental_entity_type')}")
if not rev or not almost(rev.get("metric_value"), "98770.38"):
    defects.append(f"HDFCLIFE revenue {rev}")
if not rev or rev.get("status") != "KNOWN":
    defects.append(f"HDFCLIFE revenue status {None if not rev else rev.get('status')}")
if prov.get("source_line_item") != INSURANCE_LINE:
    defects.append(f"HDFCLIFE source line {prov.get('source_line_item')}")
if prov.get("source_line_item") in ("Revenue from Operations", "Total Income"):
    defects.append("HDFCLIFE ambiguous source line")

try:
    get("/api/evidence/stocks/999999")
    defects.append("invalid stock did not 404")
except HTTPError as exc:
    print("INVALID_STOCK", exc.code)
    if exc.code != 404:
        defects.append(f"invalid stock {exc.code}")

st, market = get("/api/evidence/market-data")
m_by = {row["nse_symbol"]: row for row in market.get("items") or []}
batch_a = ["ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO", "BAJAJFINSV", "BAJFINANCE", "BEL", "BHARTIARTL"]
for sym in list(BATCH_B) + batch_a:
    row = m_by.get(sym)
    if not row:
        defects.append(f"{sym} missing market-data")
        continue
    if row.get("session_count") != 247:
        defects.append(f"{sym} sessions {row.get('session_count')}")
    if not row.get("sma200_ready"):
        defects.append(f"{sym} sma200_ready false")
    latest = str(row.get("latest_trading_date") or "")[:10]
    if latest != "2026-08-13":
        defects.append(f"{sym} latest date {latest}")

print("DEFECTS", defects)
c.close()
if defects:
    raise SystemExit(1)
print("API_VALIDATION_OK")
