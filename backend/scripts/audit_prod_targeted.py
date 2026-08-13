"""Targeted audit of production DB for Stage 6 review."""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'swing_trading.db')

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

print('=== DETAILED STOCK MASTER ===')
cur.execute('SELECT stock_id, nse_symbol, bse_symbol, company_name, isin, sector, listing_status FROM stock_master')
for s in cur.fetchall():
    print(f'  {s}')

print('\n=== DETAILED RECOMMENDATIONS ===')
cur.execute('''SELECT r.recommendation_id, sm.nse_symbol, bm.canonical_name, r.original_rating, r.normalized_rating,
               r.recommendation_date, r.target_price, r.recommended_price, r.stop_loss,
               r.analyst_name, r.lifecycle_status, r.import_batch_id, r.fingerprint
               FROM broker_recommendation r
               JOIN stock_master sm ON r.stock_id = sm.stock_id
               JOIN broker_master bm ON r.broker_id = bm.broker_id''')
for r in cur.fetchall():
    print(f'  {r}')

print('\n=== SOURCE TYPE MASTER ===')
cur.execute('SELECT source_type_id, type_name, description FROM source_type_master')
for s in cur.fetchall():
    print(f'  {s}')

print('\n=== DETAILED SOURCE REFERENCES ===')
cur.execute('''SELECT sr.source_reference_id, st.type_name, sr.publication_name, sr.url, 
               sr.source_date, sr.verification_status, sr.original_text
               FROM source_reference sr 
               JOIN source_type_master st ON sr.source_type_id = st.source_type_id''')
for s in cur.fetchall():
    print(f'  {s}')

print('\n=== RECOMMENDATION_SOURCE LINKS ===')
cur.execute('SELECT recommendation_id, source_reference_id FROM recommendation_source')
for s in cur.fetchall():
    print(f'  {s}')

conn.close()
print('\nTargeted audit complete.')
