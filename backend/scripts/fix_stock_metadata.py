"""Fix RELIANCE and TCS stock metadata correctly."""
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'swing_trading.db')
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Check current state
cur.execute("SELECT stock_id, nse_symbol, company_name, isin, listing_status FROM stock_master")
for s in cur.fetchall():
    print(f"  {s}")

# TCS has INE002A01018 which is actually RELIANCE's ISIN - fix both
# RELIANCE Industries Limited - NSE: RELIANCE - ISIN: INE002A01018
# TCS - NSE: TCS - ISIN: INE467B01029

# First nullify TCS's incorrect ISIN
cur.execute("UPDATE stock_master SET isin = NULL WHERE nse_symbol = 'TCS'")
print(f"Cleared TCS ISIN: {cur.rowcount}")

# Now set RELIANCE correctly
cur.execute("""
    UPDATE stock_master SET
        listing_status = 'ACTIVE',
        company_name = 'Reliance Industries Limited',
        isin = 'INE002A01018'
    WHERE nse_symbol = 'RELIANCE'
""")
print(f"Updated RELIANCE: {cur.rowcount}")

# Now set TCS correctly
cur.execute("""
    UPDATE stock_master SET
        company_name = 'Tata Consultancy Services Limited',
        isin = 'INE467B01029',
        listing_status = 'ACTIVE'
    WHERE nse_symbol = 'TCS'
""")
print(f"Updated TCS: {cur.rowcount}")

conn.commit()

# Verify
cur.execute("SELECT stock_id, nse_symbol, company_name, isin, listing_status FROM stock_master")
print("\nFinal state:")
for s in cur.fetchall():
    print(f"  {s}")

conn.close()
print("Done.")
