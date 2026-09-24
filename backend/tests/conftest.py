import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.database import Base, get_db, _attach_sqlite_pragma
from app.main import app
from app.config import settings

@pytest.fixture(scope="session")
def engine(tmp_path_factory):
    # Isolated temporary database for tests
    db_path = tmp_path_factory.mktemp("data") / "test_swing_trading.db"
    test_db_url = f"sqlite:///{db_path}"
    
    engine = create_engine(
        test_db_url, connect_args={"check_same_thread": False}
    )
    
    event.listen(Engine, "connect", _attach_sqlite_pragma)
    
    Base.metadata.create_all(bind=engine)
    from tests.schema_helpers import stamp_head
    stamp_head(engine)
    yield engine
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def db_session(engine):
    # Clear tables before each test
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    # Add base master data required for tests
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    
    from app.models import StockMaster, BrokerMaster, SourceTypeMaster, RatingNormalization
    db.add(StockMaster(nse_symbol='RELIANCE', company_name='Reliance Ind'))
    db.add(BrokerMaster(display_name='HDFC Securities', canonical_name='HDFC Securities', normalized_name='HDFC SECURITIES'))
    db.add(BrokerMaster(display_name='ICICI Direct', canonical_name='ICICI Direct', normalized_name='ICICI DIRECT'))
    db.add(SourceTypeMaster(type_name='BROKER_RESEARCH'))
    db.add(RatingNormalization(original_rating='BUY', normalized_rating='BUY'))
    db.add(RatingNormalization(original_rating='SELL', normalized_rating='SELL'))
    db.commit()
    
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
            
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
