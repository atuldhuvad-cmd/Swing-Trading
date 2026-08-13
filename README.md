# Swing Trading Platform

> This Swing Trading / Broker Recommendation module is strictly for personal use only and is not intended for commercial purposes, SaaS, resale, subscriptions, external customers, or multi-tenant deployment.

> Mobile-friendly responsive operation is mandatory from Phase 1.

> Phase 1 builds a Broker Recommendation Universe for NSE cash equities. Broker recommendations are candidate evidence and are NOT Buy/Sell trade signals.

Architecture Baseline: Phase 1 Architecture v2.1.1 FINAL FROZEN

Official Working Path: `D:\Swing Trading`

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
