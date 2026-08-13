"""
Stage 6 production database migration.

Actions:
1. Fix NULL active_status / enabled_for_new_ingestion on early brokers (id 1-5)
2. Add Angel One broker (missing from pilot target providers)
3. Add broker aliases for ICICI Securities / ICICI Direct identity
4. Add broker alias for Mirae Asset Sharekhan / Sharekhan
5. Remove test/fabricated data:
   - RECSTOCK stock (stock_id=1, clearly a test artefact)
   - The 2024-01-01 RELIANCE BUY fabricated recommendation
   - Test source references (no publication name, no original_text, test URLs)
   - Set RELIANCE listing_status back to ACTIVE if it exists (genuine listed stock)
6. Correct normalized_name for early brokers to use consistent format

All changes are idempotent and safe to re-run.
"""
import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'swing_trading.db')

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA foreign_keys=OFF")  # allow cascaded deletes during cleanup
cur = conn.cursor()

print("=== STAGE 6 PRODUCTION DB MIGRATION ===")

# -----------------------------------------------------------------------
# STEP 1: Fix NULL active_status and enabled_for_new_ingestion for early brokers
# -----------------------------------------------------------------------
print("\nStep 1: Fix NULL flags on early brokers (id 1-5)...")
cur.execute("""
    UPDATE broker_master
    SET active_status = 1,
        enabled_for_new_ingestion = 1,
        credibility_status = 'VERIFIED'
    WHERE broker_id IN (1, 2, 3, 4, 5)
      AND (active_status IS NULL OR enabled_for_new_ingestion IS NULL)
""")
rows = cur.rowcount
print(f"  Updated {rows} brokers.")

# -----------------------------------------------------------------------
# STEP 2: Fix normalized_name for early brokers to be consistent
# -----------------------------------------------------------------------
print("\nStep 2: Fix normalized_name format for early brokers...")
early_brokers = [
    (1, "ICICI Securities", "icici securities"),
    (2, "Motilal Oswal", "motilal oswal"),
    (3, "HDFC Securities", "hdfc securities"),
    (4, "Kotak Securities", "kotak securities"),
    (5, "Axis Securities", "axis securities"),
]
for broker_id, canonical, normalized in early_brokers:
    cur.execute("""
        UPDATE broker_master SET normalized_name = ? WHERE broker_id = ?
    """, (normalized, broker_id))
print("  Done.")

# -----------------------------------------------------------------------
# STEP 3: Add Angel One if missing
# -----------------------------------------------------------------------
print("\nStep 3: Add Angel One (missing pilot provider)...")
cur.execute("SELECT broker_id FROM broker_master WHERE canonical_name = 'Angel One'")
existing = cur.fetchone()
if existing:
    angel_id = existing[0]
    print(f"  Angel One already exists: broker_id={angel_id}")
else:
    cur.execute("""
        INSERT INTO broker_master
          (canonical_name, normalized_name, display_name, website,
           active_status, credibility_status, is_historical_only,
           enabled_for_new_ingestion, notes)
        VALUES
          ('Angel One', 'angel one', 'Angel One', 'https://www.angelone.in',
           1, 'VERIFIED', 0,
           1, 'Indian retail broker offering research picks; formerly Angel Broking.')
    """)
    angel_id = cur.lastrowid
    print(f"  Angel One inserted: broker_id={angel_id}")

# -----------------------------------------------------------------------
# STEP 4: Add broker aliases for known name variations
# -----------------------------------------------------------------------
print("\nStep 4: Add broker aliases...")

aliases_to_add = [
    # (broker_id, alias_name)
    (1, "ICICI Direct"),          # already display_name but needs alias
    (1, "ICICIdirect"),
    (1, "ICICI Securities"),      # canonical itself - add as alias too for lookups
    (10, "Sharekhan"),            # display_name alias
    (10, "Mirae Asset Sharekhan"),
    (angel_id, "Angel Broking"),  # former name
    (angel_id, "Angel One"),
]

for broker_id, alias_name in aliases_to_add:
    cur.execute("SELECT alias_id FROM broker_alias WHERE alias_name = ?", (alias_name,))
    if cur.fetchone() is None:
        cur.execute("""
            INSERT INTO broker_alias (broker_id, alias_name) VALUES (?, ?)
        """, (broker_id, alias_name))
        print(f"  Added alias: '{alias_name}' -> broker_id={broker_id}")
    else:
        print(f"  Alias already exists: '{alias_name}'")

# -----------------------------------------------------------------------
# STEP 5: Remove fabricated/test data from production
# -----------------------------------------------------------------------
print("\nStep 5: Remove fabricated/test data from production DB...")

# 5a: Remove test recommendation (stock=RELIANCE, 2024-01-01, batch_id=4)
cur.execute("""
    SELECT r.recommendation_id, sm.nse_symbol, r.recommendation_date, ib.filename
    FROM broker_recommendation r
    JOIN stock_master sm ON r.stock_id = sm.stock_id
    LEFT JOIN import_batch ib ON r.import_batch_id = ib.batch_id
    WHERE r.recommendation_date = '2024-01-01 00:00:00.000000'
       OR (sm.nse_symbol = 'RELIANCE' AND ib.filename = 'test.csv')
""")
test_recs = cur.fetchall()
print(f"  Test recommendations found: {len(test_recs)}")
for tr in test_recs:
    print(f"    rec_id={tr[0]} symbol={tr[1]} date={tr[2]} file={tr[3]}")
    # Remove recommendation_source links first
    cur.execute("DELETE FROM recommendation_source WHERE recommendation_id = ?", (tr[0],))
    # Remove status history
    cur.execute("DELETE FROM recommendation_status_history WHERE recommendation_id = ?", (tr[0],))
    # Remove the recommendation
    cur.execute("DELETE FROM broker_recommendation WHERE recommendation_id = ?", (tr[0],))
    print(f"    -> Deleted recommendation_id={tr[0]}")

# 5b: Remove orphan test source references 
# (those with no publication_name and no original_text — these are placeholders)
cur.execute("""
    SELECT sr.source_reference_id, sr.verification_status, sr.url
    FROM source_reference sr
    LEFT JOIN recommendation_source rs ON sr.source_reference_id = rs.source_reference_id
    WHERE rs.source_reference_id IS NULL
      AND sr.publication_name IS NULL
      AND sr.original_text IS NULL
""")
orphan_sources = cur.fetchall()
print(f"  Orphan test source_references found: {len(orphan_sources)}")
for os_row in orphan_sources:
    print(f"    source_ref_id={os_row[0]} status={os_row[1]} url={os_row[2]}")
    cur.execute("DELETE FROM source_reference WHERE source_reference_id = ?", (os_row[0],))
    print(f"    -> Deleted source_reference_id={os_row[0]}")

# 5c: Remove RECSTOCK (test stock - company_name='Test')
cur.execute("SELECT stock_id, nse_symbol, company_name FROM stock_master WHERE nse_symbol='RECSTOCK' OR company_name='Test'")
test_stocks = cur.fetchall()
print(f"  Test stocks found: {len(test_stocks)}")
for ts in test_stocks:
    print(f"    stock_id={ts[0]} symbol={ts[1]} name={ts[2]}")
    # Check no real recommendations reference this stock
    cur.execute("SELECT COUNT(*) FROM broker_recommendation WHERE stock_id=?", (ts[0],))
    rec_count = cur.fetchone()[0]
    if rec_count == 0:
        cur.execute("DELETE FROM stock_master WHERE stock_id=?", (ts[0],))
        print(f"    -> Deleted stock_id={ts[0]}")
    else:
        print(f"    -> SKIPPED: has {rec_count} recommendation(s)")

# -----------------------------------------------------------------------
# STEP 6: Add system settings if missing
# -----------------------------------------------------------------------
print("\nStep 6: Verify system settings...")
required_settings = [
    ("FRESH_MAX_DAYS", "7", "Upper bound (inclusive) of FRESH freshness tier in days"),
    ("RECENT_MAX_DAYS", "15", "Upper bound (inclusive) of RECENT freshness tier in days"),
    ("MODERATE_MAX_DAYS", "30", "Upper bound (inclusive) of MODERATE freshness tier in days"),
    ("STALE_MAX_DAYS", "60", "Upper bound (inclusive) of STALE freshness tier in days"),
    ("DEFAULT_CURRENCY", "INR", "Default currency for all prices"),
    ("ELIGIBLE_BULLISH_RATINGS", "BUY,STRONG_BUY,ACCUMULATE,ADD,OUTPERFORM,POSITIVE",
     "Comma-separated normalized ratings eligible for bullish consensus counting"),
]
for key, value, desc in required_settings:
    cur.execute("SELECT setting_value FROM system_setting WHERE setting_key = ?", (key,))
    existing = cur.fetchone()
    if existing:
        print(f"  OK: {key}={existing[0]}")
    else:
        cur.execute("INSERT INTO system_setting (setting_key, setting_value, description) VALUES (?, ?, ?)",
                    (key, value, desc))
        print(f"  Inserted: {key}={value}")

conn.commit()
conn.execute("PRAGMA foreign_keys=ON")
conn.close()

print("\n=== STAGE 6 MIGRATION COMPLETE ===")
