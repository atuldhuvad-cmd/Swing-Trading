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
    yield engine
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def db_session(engine):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
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
