"""Schema readiness: the database must be at the repository's Alembic head.

Disposable databases only. The check must never migrate or modify a database.
"""
import hashlib
import importlib.util
import logging
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import schema_readiness as sr
from app.database import Base, get_db
from app.main import app
from tests.migration_helpers import alembic
from tests.schema_helpers import stamp_head

ROOT = Path(__file__).resolve().parents[2]
PREVIOUS = "f2a7c9d41b3e"


def _db(tmp_path, name, revision="head-stamp"):
    """A models-built database: no alembic_version, a given revision, or the head."""
    path = tmp_path / name
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    if revision == "head-stamp":
        stamp_head(engine)
    elif revision is not None:
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
            conn.exec_driver_sql("INSERT INTO alembic_version VALUES (?)", (revision,))
    return path, engine


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def client_for():
    engines = []

    def make(engine):
        engines.append(engine)
        Session = sessionmaker(bind=engine)

        def override():
            s = Session()
            try:
                yield s
            finally:
                s.close()

        sr.reset_cache()
        app.dependency_overrides[get_db] = override
        return TestClient(app)

    yield make
    app.dependency_overrides.clear()
    sr.reset_cache()
    for e in engines:
        e.dispose()


@pytest.mark.parametrize("revision,state", [
    (None, sr.MISSING), (PREVIOUS, sr.BEHIND), ("0000deadbeef", sr.UNEXPECTED), ("head-stamp", sr.CURRENT)])
def test_check_schema_states_without_mutation(tmp_path, revision, state):
    path, engine = _db(tmp_path, "s.db", revision)
    engine.dispose()
    before = _sha(path)
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as conn:
        status = sr.check_schema(conn)
    engine.dispose()
    assert status.state == state and status.expected_revision == sr.expected_head()
    assert _sha(path) == before  # the check never writes


def test_empty_alembic_version_table_is_missing(tmp_path):
    path, engine = _db(tmp_path, "e.db", None)
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
    with engine.connect() as conn:
        assert sr.check_schema(conn).state == sr.MISSING
    engine.dispose()


def test_real_previous_revision_is_behind_and_head_is_current(tmp_path):
    db = tmp_path / "real.db"
    alembic(db, "upgrade", PREVIOUS)
    engine = create_engine(f"sqlite:///{db}")
    with engine.connect() as conn:
        assert sr.check_schema(conn).state == sr.BEHIND
    engine.dispose()
    alembic(db, "upgrade", "head")
    engine = create_engine(f"sqlite:///{db}")
    with engine.connect() as conn:
        assert sr.check_schema(conn).state == sr.CURRENT
    engine.dispose()


@pytest.mark.parametrize("revision", [None, PREVIOUS, "0000deadbeef"])
def test_api_routes_refuse_with_controlled_503(tmp_path, client_for, revision):
    path, engine = _db(tmp_path, "n.db", revision)
    before = _sha(path)
    client = client_for(engine)
    for route in ("/api/stocks", "/api/broker-uploads", "/api/recommendations"):
        resp = client.get(route)
        assert resp.status_code == 503, route
        detail = resp.json()["detail"]
        assert detail["error"] == "SCHEMA_NOT_CURRENT" and detail["expected_revision"] == sr.expected_head()
        assert "alembic upgrade head" in detail["action"]
        for leak in ("SELECT", "sqlite", "Traceback", str(tmp_path)):
            assert leak not in resp.text
    resp = client.post("/api/stocks", json={"nse_symbol": "SYNTH", "company_name": "Synthetic"})
    assert resp.status_code == 503
    engine.dispose()
    assert _sha(path) == before  # nothing was written, and nothing was migrated
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM stock_master").fetchone()[0] == 0


@pytest.mark.parametrize("revision,state", [(None, sr.MISSING), (PREVIOUS, sr.BEHIND), ("0000deadbeef", sr.UNEXPECTED)])
def test_health_reports_non_current_schema(tmp_path, client_for, revision, state):
    _, engine = _db(tmp_path, "h.db", revision)
    resp = client_for(engine).get("/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "schema_not_current" and body["schema"]["state"] == state
    assert "alembic upgrade head" in body["action"] and str(tmp_path) not in resp.text


def test_current_database_behaves_as_before(tmp_path, client_for):
    _, engine = _db(tmp_path, "c.db")
    client = client_for(engine)
    health = client.get("/health")
    assert health.status_code == 200 and health.json()["status"] == "ok"
    assert health.json()["schema"]["state"] == sr.CURRENT
    assert client.get("/api/stocks").status_code == 200
    assert client.post("/api/stocks", json={"nse_symbol": "SYNTH", "company_name": "Synthetic"}).status_code == 200


def test_startup_log_gives_a_concise_instruction(tmp_path, caplog):
    _, engine = _db(tmp_path, "l.db", PREVIOUS)
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        sr.log_startup_status(engine)
    engine.dispose()
    assert any("BEHIND" in r.getMessage() and "alembic upgrade head" in r.getMessage() for r in caplog.records)


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), ROOT / "scratch" / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _never(*_a, **_k):
    raise AssertionError("must not be reached before the schema check")


def test_icici_import_refuses_before_any_write_on_stale_schema(tmp_path, monkeypatch):
    mod = _load_script("auto_download_broker_recs_icici.py")
    path, engine = _db(tmp_path, "icici.db", PREVIOUS)
    before = _sha(path)
    monkeypatch.setattr(mod, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(mod, "backup_database", _never)
    monkeypatch.setattr(mod, "plan_import", _never)

    class Args:
        import_min_confidence = 0.9
        max_imports = 25

    summary, code = mod.run_import(Args, [], 100, path, False, "s")
    engine.dispose()
    assert code == 3 and "schema is BEHIND" in summary["refused"]
    assert _sha(path) == before


def test_ohlcv_refuses_before_backup_or_download_on_missing_schema(tmp_path, monkeypatch, capsys):
    mod = _load_script("auto_download_ohlcv.py")
    path, engine = _db(tmp_path, "ohlcv.db", None)
    before = _sha(path)
    monkeypatch.setattr(mod, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(mod, "configured_db_path", lambda: path)
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path / "out")
    for name in ("backup_database", "run_bhavcopy", "run_symbols"):
        monkeypatch.setattr(mod, name, _never)
    monkeypatch.setattr(mod.sys, "argv", ["auto_download_ohlcv.py"])
    code = mod.main()
    engine.dispose()
    assert code == 3 and "schema is MISSING" in capsys.readouterr().out
    assert _sha(path) == before
