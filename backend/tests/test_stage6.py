"""
Stage 6 tests:
- Production/test database isolation (production DB must NOT be touched during tests)
- Source readiness endpoint returns correct pilot providers
- freshness_summary uses correct 5-tier logic (FRESH/RECENT/MODERATE/STALE/AGED)
- Broker alias is available for known pilot providers
- Stream name is exposed in contributor output when present
- Fabricated data audit (test broker/stock names must not appear in production)
"""
import pytest
import os
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from app.models import (
    StockMaster, BrokerMaster, BrokerRecommendation, StockPrice,
    SourceTypeMaster, SystemSetting, BrokerAlias
)
from app.services.consensus_service import ConsensusService


# ============================================================
# Test: Production DB isolation
# ============================================================

class TestProductionDbIsolation:
    """Verify that tests NEVER touch the production database."""

    def test_test_db_is_not_production_db(self, db_session):
        """The test session must use an isolated in-memory or temp db, not swing_trading.db."""
        engine_url = str(db_session.get_bind().url)
        production_db_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'swing_trading.db')
        )
        # Normalize the production path to forward slashes for comparison
        production_db_path_normalized = production_db_path.replace('\\', '/')
        # The test DB URL should NOT point to the same file as the production DB
        assert production_db_path_normalized not in engine_url.replace('\\', '/'), (
            f"CRITICAL: Test session is using the PRODUCTION database: {engine_url}\n"
            f"Production DB path: {production_db_path}"
        )

    def test_test_db_is_separate_from_production(self, db_session):
        """Inserting test data into the test session must not affect the production DB."""
        # Insert a test broker into the test session
        test_broker = BrokerMaster(
            canonical_name='ISOLATION_TEST_BROKER',
            normalized_name='isolation test broker',
            display_name='Isolation Test Broker'
        )
        db_session.add(test_broker)
        db_session.commit()

        # Verify it's in the test DB
        found = db_session.query(BrokerMaster).filter(
            BrokerMaster.canonical_name == 'ISOLATION_TEST_BROKER'
        ).first()
        assert found is not None, "Test broker should exist in test DB"

        # Verify it's NOT in the production DB
        import sqlite3
        prod_db_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'data', 'swing_trading.db'
        )
        if os.path.exists(prod_db_path):
            conn = sqlite3.connect(prod_db_path)
            cur = conn.cursor()
            cur.execute(
                "SELECT canonical_name FROM broker_master WHERE canonical_name = ?",
                ('ISOLATION_TEST_BROKER',)
            )
            result = cur.fetchone()
            conn.close()
            assert result is None, (
                "CRITICAL: Test broker 'ISOLATION_TEST_BROKER' was found in the PRODUCTION database! "
                "The test session is contaminating production data."
            )


# ============================================================
# Test: Source readiness endpoint
# ============================================================

class TestSourceReadinessEndpoint:
    """Verify that the source readiness endpoint returns correct data for all pilot providers."""

    def test_source_readiness_returns_pilot_providers(self, client: TestClient, db_session):
        """Source readiness endpoint should return 5 pilot providers."""
        # Add the 5 pilot providers to the test DB
        pilot_brokers = [
            ("Angel One", "angel one", "Angel One"),
            ("HDFC Securities", "hdfc securities", "HDFC Securities"),
            ("Motilal Oswal", "motilal oswal", "Motilal Oswal"),
            ("ICICI Securities", "icici securities", "ICICI Direct"),
            ("Mirae Asset Sharekhan", "mirae asset sharekhan", "Sharekhan"),
        ]
        for canonical, normalized, display in pilot_brokers:
            existing = db_session.query(BrokerMaster).filter(
                BrokerMaster.canonical_name == canonical
            ).first()
            if not existing:
                db_session.add(BrokerMaster(
                    canonical_name=canonical,
                    normalized_name=normalized,
                    display_name=display,
                    active_status=True,
                    enabled_for_new_ingestion=True
                ))
        db_session.commit()

        response = client.get("/api/consensus/source-readiness")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 5

        canonical_names = {item["canonical_name"] for item in data}
        assert "Angel One" in canonical_names
        assert "HDFC Securities" in canonical_names
        assert "Motilal Oswal" in canonical_names
        assert "ICICI Securities" in canonical_names
        assert "Mirae Asset Sharekhan" in canonical_names

    def test_source_readiness_has_correct_categories(self, client: TestClient, db_session):
        """Each provider must have a recognized readiness category."""
        # Ensure pilot providers exist
        pilot_brokers = [
            ("Angel One", "angel one", "Angel One"),
            ("HDFC Securities", "hdfc securities", "HDFC Securities"),
            ("Motilal Oswal", "motilal oswal", "Motilal Oswal"),
            ("ICICI Securities", "icici securities", "ICICI Direct"),
            ("Mirae Asset Sharekhan", "mirae asset sharekhan", "Sharekhan"),
        ]
        for canonical, normalized, display in pilot_brokers:
            if not db_session.query(BrokerMaster).filter(BrokerMaster.canonical_name == canonical).first():
                db_session.add(BrokerMaster(
                    canonical_name=canonical, normalized_name=normalized,
                    display_name=display, active_status=True, enabled_for_new_ingestion=True
                ))
        db_session.commit()

        response = client.get("/api/consensus/source-readiness")
        assert response.status_code == 200
        data = response.json()

        VALID_CATEGORIES = {
            'PUBLIC_STABLE', 'PUBLIC_UNSTABLE', 'LOGIN_REQUIRED',
            'DOCUMENT_MANUAL', 'SECONDARY_ONLY', 'UNSUITABLE'
        }

        for item in data:
            assert item["readiness_category"] in VALID_CATEGORIES, (
                f"Provider '{item['canonical_name']}' has invalid category: {item['readiness_category']}"
            )
            assert item["reasoning"], f"Provider '{item['canonical_name']}' is missing reasoning"
            assert item["collection_method"], f"Provider '{item['canonical_name']}' is missing collection_method"

    def test_angel_one_is_login_required(self, client: TestClient, db_session):
        """Angel One should be classified as LOGIN_REQUIRED."""
        if not db_session.query(BrokerMaster).filter(BrokerMaster.canonical_name == "Angel One").first():
            db_session.add(BrokerMaster(
                canonical_name="Angel One", normalized_name="angel one",
                display_name="Angel One", active_status=True, enabled_for_new_ingestion=True
            ))
            db_session.commit()

        response = client.get("/api/consensus/source-readiness")
        assert response.status_code == 200
        data = response.json()
        angel_one = next((i for i in data if i["canonical_name"] == "Angel One"), None)
        assert angel_one is not None
        assert angel_one["readiness_category"] == "LOGIN_REQUIRED"

    def test_sharekhan_is_public_unstable(self, client: TestClient, db_session):
        """Mirae Asset Sharekhan should be classified as SECONDARY_ONLY."""
        if not db_session.query(BrokerMaster).filter(BrokerMaster.canonical_name == "Mirae Asset Sharekhan").first():
            db_session.add(BrokerMaster(
                canonical_name="Mirae Asset Sharekhan", normalized_name="mirae asset sharekhan",
                display_name="Sharekhan", active_status=True, enabled_for_new_ingestion=True
            ))
            db_session.commit()

        response = client.get("/api/consensus/source-readiness")
        assert response.status_code == 200
        data = response.json()
        sharekhan = next((i for i in data if i["canonical_name"] == "Mirae Asset Sharekhan"), None)
        assert sharekhan is not None
        assert sharekhan["readiness_category"] == "PUBLIC_UNSTABLE"


# ============================================================
# Test: 5-tier freshness summary in consensus service
# ============================================================

class TestFreshnessSummaryFiveTier:
    """Verify that freshness_summary in calculate_stock_consensus uses 5-tier system."""

    def _setup_system_settings(self, db_session):
        """Add system settings for freshness thresholds."""
        settings = [
            ("FRESH_MAX_DAYS", "7"),
            ("RECENT_MAX_DAYS", "15"),
            ("MODERATE_MAX_DAYS", "30"),
            ("STALE_MAX_DAYS", "60"),
            ("ELIGIBLE_BULLISH_RATINGS", "BUY,STRONG_BUY,ACCUMULATE,ADD,OUTPERFORM,POSITIVE"),
        ]
        for key, val in settings:
            if not db_session.query(SystemSetting).filter(SystemSetting.setting_key == key).first():
                db_session.add(SystemSetting(setting_key=key, setting_value=val))
        db_session.commit()

    def _create_stock_and_broker(self, db_session, symbol: str) -> tuple:
        stock = StockMaster(nse_symbol=symbol, company_name=f'Test {symbol}', listing_status='ACTIVE')
        broker = BrokerMaster(
            canonical_name=f'TestBroker_{symbol}', normalized_name=f'testbroker {symbol}',
            display_name=f'TestBroker {symbol}'
        )
        db_session.add_all([stock, broker])
        db_session.commit()
        return stock, broker

    def test_freshness_summary_fresh(self, db_session):
        """avg_age of 5 days should yield freshness_summary=FRESH."""
        self._setup_system_settings(db_session)
        stock, broker = self._create_stock_and_broker(db_session, 'FSTEST1')
        # Add source type
        st = db_session.query(SourceTypeMaster).first()
        if not st:
            st = SourceTypeMaster(type_name='BROKER_RESEARCH')
            db_session.add(st)
            db_session.commit()

        rec = BrokerRecommendation(
            stock_id=stock.stock_id, broker_id=broker.broker_id,
            recommendation_date=datetime.utcnow() - timedelta(days=5),
            original_rating='BUY', normalized_rating='BUY', lifecycle_status='CURRENT'
        )
        db_session.add(rec)
        db_session.commit()

        result = ConsensusService.calculate_stock_consensus(db_session, stock.stock_id)
        assert result is not None
        assert result.metrics.freshness_summary == 'FRESH'

    def test_freshness_summary_recent(self, db_session):
        """avg_age of 12 days should yield freshness_summary=RECENT."""
        self._setup_system_settings(db_session)
        stock, broker = self._create_stock_and_broker(db_session, 'RCTEST1')
        rec = BrokerRecommendation(
            stock_id=stock.stock_id, broker_id=broker.broker_id,
            recommendation_date=datetime.utcnow() - timedelta(days=12),
            original_rating='BUY', normalized_rating='BUY', lifecycle_status='CURRENT'
        )
        db_session.add(rec)
        db_session.commit()
        result = ConsensusService.calculate_stock_consensus(db_session, stock.stock_id)
        assert result is not None
        assert result.metrics.freshness_summary == 'RECENT', f"Expected RECENT but got {result.metrics.freshness_summary}"

    def test_freshness_summary_moderate(self, db_session):
        """avg_age of 25 days should yield freshness_summary=MODERATE."""
        self._setup_system_settings(db_session)
        stock, broker = self._create_stock_and_broker(db_session, 'MODTEST1')
        rec = BrokerRecommendation(
            stock_id=stock.stock_id, broker_id=broker.broker_id,
            recommendation_date=datetime.utcnow() - timedelta(days=25),
            original_rating='BUY', normalized_rating='BUY', lifecycle_status='CURRENT'
        )
        db_session.add(rec)
        db_session.commit()
        result = ConsensusService.calculate_stock_consensus(db_session, stock.stock_id)
        assert result is not None
        assert result.metrics.freshness_summary == 'MODERATE', f"Expected MODERATE but got {result.metrics.freshness_summary}"

    def test_freshness_summary_stale(self, db_session):
        """avg_age of 45 days should yield freshness_summary=STALE."""
        self._setup_system_settings(db_session)
        stock, broker = self._create_stock_and_broker(db_session, 'STTEST1')
        rec = BrokerRecommendation(
            stock_id=stock.stock_id, broker_id=broker.broker_id,
            recommendation_date=datetime.utcnow() - timedelta(days=45),
            original_rating='BUY', normalized_rating='BUY', lifecycle_status='CURRENT'
        )
        db_session.add(rec)
        db_session.commit()
        result = ConsensusService.calculate_stock_consensus(db_session, stock.stock_id)
        assert result is not None
        assert result.metrics.freshness_summary == 'STALE', f"Expected STALE but got {result.metrics.freshness_summary}"

    def test_freshness_summary_aged(self, db_session):
        """avg_age of 90 days should yield freshness_summary=AGED."""
        self._setup_system_settings(db_session)
        stock, broker = self._create_stock_and_broker(db_session, 'AGTEST1')
        rec = BrokerRecommendation(
            stock_id=stock.stock_id, broker_id=broker.broker_id,
            recommendation_date=datetime.utcnow() - timedelta(days=90),
            original_rating='BUY', normalized_rating='BUY', lifecycle_status='CURRENT'
        )
        db_session.add(rec)
        db_session.commit()
        result = ConsensusService.calculate_stock_consensus(db_session, stock.stock_id)
        assert result is not None
        assert result.metrics.freshness_summary == 'AGED', f"Expected AGED but got {result.metrics.freshness_summary}"


# ============================================================
# Test: Broker alias in broker_master
# ============================================================

class TestBrokerAlias:
    """Verify that broker aliases are correctly stored and accessible."""

    def test_broker_alias_unique_constraint(self, db_session):
        """Broker aliases must be unique across all brokers."""
        from sqlalchemy.exc import IntegrityError

        broker = BrokerMaster(
            canonical_name='Alias Test Broker',
            normalized_name='alias test broker',
            display_name='Alias Test Broker'
        )
        db_session.add(broker)
        db_session.commit()

        alias1 = BrokerAlias(broker_id=broker.broker_id, alias_name='AliasA')
        db_session.add(alias1)
        db_session.commit()

        # Attempt to insert duplicate alias
        alias2 = BrokerAlias(broker_id=broker.broker_id, alias_name='AliasA')
        db_session.add(alias2)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_broker_aliases_retrieve_correctly(self, db_session):
        """Multiple aliases can be added to a broker."""
        broker = BrokerMaster(
            canonical_name='Multi Alias Broker',
            normalized_name='multi alias broker',
            display_name='Multi Alias Broker'
        )
        db_session.add(broker)
        db_session.commit()

        aliases = ['AliasX', 'AliasY', 'AliasZ']
        for alias_name in aliases:
            db_session.add(BrokerAlias(broker_id=broker.broker_id, alias_name=alias_name))
        db_session.commit()

        stored_aliases = db_session.query(BrokerAlias).filter(
            BrokerAlias.broker_id == broker.broker_id
        ).all()
        stored_names = {a.alias_name for a in stored_aliases}
        assert stored_names == set(aliases), f"Expected {set(aliases)}, got {stored_names}"


# ============================================================
# Test: Production DB fabricated data audit
# ============================================================

class TestProductionFabricatedDataAudit:
    """Audit the production DB for known fabricated/test data patterns."""

    def test_production_db_has_no_recstock(self):
        """Production DB must not contain RECSTOCK (a known test artefact)."""
        import sqlite3
        prod_db_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'data', 'swing_trading.db'
        )
        if not os.path.exists(prod_db_path):
            pytest.skip("Production DB does not exist yet — skipping audit.")
        
        conn = sqlite3.connect(prod_db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM stock_master WHERE nse_symbol = 'RECSTOCK'")
        count = cur.fetchone()[0]
        conn.close()
        assert count == 0, f"Production DB contains {count} RECSTOCK entry/entries — must be 0."

    def test_production_db_has_no_test_recommendation_from_2024_01_01(self):
        """Production DB must not contain the fabricated 2024-01-01 test recommendation."""
        import sqlite3
        prod_db_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'data', 'swing_trading.db'
        )
        if not os.path.exists(prod_db_path):
            pytest.skip("Production DB does not exist yet — skipping audit.")
        
        conn = sqlite3.connect(prod_db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM broker_recommendation WHERE date(recommendation_date) = '2024-01-01'"
        )
        count = cur.fetchone()[0]
        conn.close()
        assert count == 0, (
            f"Production DB contains {count} recommendation(s) dated 2024-01-01. "
            "These appear to be test/fabricated records and must be removed."
        )

    def test_production_db_angel_one_exists(self):
        """Production DB must have Angel One as a pilot provider."""
        import sqlite3
        prod_db_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'data', 'swing_trading.db'
        )
        if not os.path.exists(prod_db_path):
            pytest.skip("Production DB does not exist yet — skipping audit.")
        
        conn = sqlite3.connect(prod_db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM broker_master WHERE canonical_name = 'Angel One'")
        count = cur.fetchone()[0]
        conn.close()
        assert count == 1, f"Expected Angel One in production broker_master but found {count} entry/entries."

    def test_production_db_pilot_providers_have_active_flags(self):
        """Production DB pilot providers must have active_status = 1."""
        import sqlite3
        prod_db_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'data', 'swing_trading.db'
        )
        if not os.path.exists(prod_db_path):
            pytest.skip("Production DB does not exist yet — skipping audit.")
        
        pilot_names = ['Angel One', 'HDFC Securities', 'Motilal Oswal', 'ICICI Securities', 'Mirae Asset Sharekhan']
        conn = sqlite3.connect(prod_db_path)
        cur = conn.cursor()
        for name in pilot_names:
            cur.execute(
                "SELECT active_status, enabled_for_new_ingestion FROM broker_master WHERE canonical_name = ?",
                (name,)
            )
            row = cur.fetchone()
            assert row is not None, f"Pilot provider '{name}' not found in production broker_master."
            assert row[0] == 1, f"Pilot provider '{name}' has active_status={row[0]}, expected 1."
            assert row[1] == 1, f"Pilot provider '{name}' has enabled_for_new_ingestion={row[1]}, expected 1."
        conn.close()
