"""Audit production database for Stage 6 baseline."""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'swing_trading.db')

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Audit broker_master
cur.execute('SELECT broker_id, canonical_name, display_name, normalized_name, active_status, enabled_for_new_ingestion, is_historical_only FROM broker_master')
brokers = cur.fetchall()
print('=== BROKER MASTER ===')
for b in brokers:
    print(f'  id={b[0]} canonical="{b[1]}" display="{b[2]}" active={b[4]} enabled={b[5]} historical={b[6]}')

# Audit broker_alias
cur.execute('SELECT alias_id, broker_id, alias_name FROM broker_alias')
aliases = cur.fetchall()
print('=== BROKER ALIASES ===')
for a in aliases:
    print(f'  alias_id={a[0]} broker_id={a[1]} alias="{a[2]}"')

# Audit broker_relationship
cur.execute('SELECT relationship_id, predecessor_id, successor_id, relationship_type, effective_date FROM broker_relationship')
rels = cur.fetchall()
print('=== BROKER RELATIONSHIPS ===')
for r in rels:
    print(f'  id={r[0]} pred={r[1]} succ={r[2]} type={r[3]} date={r[4]}')

# Audit recommendation_stream
cur.execute('SELECT stream_id, broker_id, stream_name, stream_type, frequency, enabled FROM recommendation_stream')
streams = cur.fetchall()
print('=== RECOMMENDATION STREAMS ===')
for s in streams:
    print(f'  stream_id={s[0]} broker_id={s[1]} name="{s[2]}" type={s[3]} freq={s[4]} enabled={s[5]}')

# Audit recommendations
cur.execute('SELECT COUNT(*) FROM broker_recommendation')
rec_count = cur.fetchone()[0]
print(f'=== RECOMMENDATIONS: {rec_count} total ===')

if rec_count > 0:
    cur.execute('SELECT recommendation_id, stock_id, broker_id, original_rating, lifecycle_status, recommendation_date FROM broker_recommendation LIMIT 10')
    recs = cur.fetchall()
    for r in recs:
        print(f'  rec_id={r[0]} stock_id={r[1]} broker_id={r[2]} rating={r[3]} status={r[4]} date={r[5]}')

# Audit source references
cur.execute('SELECT COUNT(*) FROM source_reference')
src_count = cur.fetchone()[0]
print(f'=== SOURCE REFERENCES: {src_count} total ===')

# Audit stock_master
cur.execute('SELECT COUNT(*) FROM stock_master')
stock_count = cur.fetchone()[0]
print(f'=== STOCKS: {stock_count} total ===')

if stock_count > 0:
    cur.execute('SELECT stock_id, nse_symbol, company_name FROM stock_master LIMIT 10')
    stocks = cur.fetchall()
    for s in stocks:
        print(f'  stock_id={s[0]} symbol={s[1]} name={s[2]}')

# Check for fabricated test data
cur.execute("SELECT canonical_name FROM broker_master WHERE canonical_name LIKE '%TEST%' OR canonical_name LIKE '%DEMO%' OR canonical_name LIKE '%SMOKE%' OR canonical_name LIKE '%FAKE%'")
test_brokers = cur.fetchall()
print(f'=== FABRICATED/TEST BROKERS: {len(test_brokers)} ===')
for t in test_brokers:
    print(f'  {t}')

cur.execute("SELECT nse_symbol FROM stock_master WHERE nse_symbol LIKE '%TEST%' OR nse_symbol LIKE '%SMOKE%' OR nse_symbol LIKE '%DEMO%'")
test_stocks = cur.fetchall()
print(f'=== FABRICATED/TEST STOCKS: {len(test_stocks)} ===')

# System settings
cur.execute('SELECT setting_key, setting_value FROM system_setting')
settings = cur.fetchall()
print('=== SYSTEM SETTINGS ===')
for s in settings:
    print(f'  {s[0]}={s[1]}')

# Rating normalization
cur.execute('SELECT original_rating, normalized_rating FROM rating_normalization')
norms = cur.fetchall()
print('=== RATING NORMALIZATIONS ===')
for n in norms:
    print(f'  "{n[0]}" -> {n[1]}')

conn.close()
print('\nAudit complete.')
