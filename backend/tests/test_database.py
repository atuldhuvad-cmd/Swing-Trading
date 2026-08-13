from sqlalchemy import text

def test_foreign_keys_enabled(db_session):
    result = db_session.execute(text("PRAGMA foreign_keys")).scalar()
    assert int(result) == 1

def test_production_db_isolation(engine):
    # Verify the test engine is not using the production URL
    from app.config import settings
    assert str(engine.url) != settings.database_url
    assert "test_swing_trading.db" in str(engine.url)
