# Swing Trading Platform

> This Swing Trading / Broker Recommendation module is strictly for personal use only and is not intended for commercial purposes, SaaS, resale, subscriptions, external customers, or multi-tenant deployment.

> Mobile-friendly responsive operation is mandatory from Phase 1.

> Phase 1 builds a Broker Recommendation Universe for NSE cash equities. Broker recommendations are candidate evidence and are NOT Buy/Sell trade signals.

Architecture Baseline: Phase 1 Architecture v2.1.1 FINAL FROZEN

Official Working Path: `D:\Swing Trading`

## Stage 7 Real-Data Pilot

The production database contains five genuine ICICI Direct recommendations verified from official public ICICI Securities Retail Equity Research PDFs. They were entered through the existing stock and recommendation APIs; no scraper, brokerage API, credential, or downloaded report was added to the repository. Only explicitly published fields are stored. Missing stop loss, live CMP, and other financial metadata remain NULL and display as N/A.

Primary evidence is marked `VERIFIED_PRIMARY`; reputable attributed publications may be `VERIFIED_SECONDARY`. Provisional or rejected evidence cannot contribute to the candidate universe. The current ICICI pilot covers CARYSIL, ASTRAMICRO, HINDALCO, GLAND, and NRBBEARING.

To add a real recommendation, verify the company and NSE symbol, add a missing stock through Stock Master, then use Recommendation Entry or the CSV/XLSX import preview and confirmation flow. Attach the official source URL, publication and source date, a traceable extract, and the appropriate verification status. Never infer absent values.

Source investigation found ICICI Direct's structured result-update listing and official PDFs public and stable enough for manual ingestion. HDFC Securities remains login-required; Motilal Oswal is public but structurally unstable; Angel One remains login-required; Mirae Asset Sharekhan now has public official research pages but multiple changing page families require manual verification. Future automation appears most feasible for ICICI Direct at a DAILY check frequency, technically possible but higher-risk for Motilal Oswal and Sharekhan at WEEKLY frequency, inappropriate for HDFC Securities and Angel One without a compliant public source, and remains outside Stage 7.

## Stage 5 Implementation
Implemented the Broker Candidate Dashboard and Consensus Service:
- Unique broker-count rule ensures multiple sources for the same recommendation do not artificially inflate consensus.
- Clear separation between lifecycle status (CURRENT/SUPERSEDED) and freshness category. Age alone does not override a CURRENT lifecycle.
- Five freshness buckets dynamically fetched from system settings (FRESH, RECENT, MODERATE, STALE, AGED).
- Default candidate universe filters out STALE and AGED recommendations (age <= 30 days) unless explicitly overridden.
- Comprehensive target statistics including average target, median target, min/max targets, and both average/median upside percentages.
- Handles CMP gracefully if unavailable.
- Advanced candidate filters for minimum brokers, upside, bullish percentage, and freshness limits.
- Stock Detail page displaying granular consensus breakdown, latest broker recommendations, and associated evidence/history.

## Stage 4 Implementation
Implemented the CSV/XLSX Import Engine, Deduplication, and Review workflows:
- Support for `csv` and `xlsx` payload uploads with robust validation, including automatic future-date rejection, target vs current price low/high checks, and rating normalization.
- Mapping capabilities dynamic against DB state, gracefully assigning statuses (`UNIQUE`, `PROBABLE_DUPLICATE`, `ATTACH_SOURCE`, `REVIEW_REQUIRED`, etc.).
- Defensive confirmation flows ensuring safe commit to production database without creating orphaned records.
- Comprehensive test coverage for import engine deduplication edge cases.

## Stage 3 Implementation
Implemented the API backend and mobile-first frontend interface for Recommendation Entry and Master Data:
- `backend/app/routers/` exposes APIs for Stocks, Brokers, Recommendations, and Reference data.
- Recommendation duplicate checks and supersession logic implemented.
- `frontend/` developed as a responsive React single-page application using Tailwind CSS.
- Seeding scripts (`backend/scripts/seed_expanded_brokers.py`) are populated with default master data.

## Stage 2 Database Model Summary
The application uses SQLite with SQLAlchemy 2.x and Alembic for migrations.
17 entities implemented:
1. `stock_master`
2. `broker_master`
3. `broker_alias`
4. `broker_relationship`
5. `recommendation_stream`
6. `broker_recommendation`
7. `recommendation_status_history`
8. `recommendation_source`
9. `source_reference`
10. `source_type_master`
11. `rating_normalization`
12. `stock_price`
13. `price_observation`
14. `import_batch`
15. `import_batch_detail`
16. `review_queue`
17. `system_setting`

## Commands

### Stage 8 rendered browser validation

Run the backend and frontend locally, capture the exact URL printed by Vite, and pass it to the Playwright suite. The suite uses the installed Chrome channel through Playwright's Chromium engine and validates the Phase 1 screens at 320, 375, 390, 768, and 1024 pixels without writing production data.

```powershell
$env:STAGE8_BASE_URL='http://127.0.0.1:<vite-port>'
npm --prefix frontend run test:e2e
```

### Migrations
```bash
# Upgrade to latest
alembic upgrade head

# Downgrade completely
alembic downgrade base
```

### Tests
```bash
# Run pytest (uses isolated temporary db)
pytest
```

## Backup Note
Since this project uses SQLite, to backup the database simply copy `backend/data/swing_trading.db`.
