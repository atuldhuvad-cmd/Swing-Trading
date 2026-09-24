"""Broker flag correction (migration c9d3f6a2e815) on disposable databases.

The initial migration seeded brokers with NULL active_status /
enabled_for_new_ingestion. Decision: seeded brokers are active and enabled.
"""
import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import schema_readiness
from app.database import get_db
from app.main import app
from tests.migration_helpers import alembic

BEFORE_FIX = "b5e8c2d17a40"
TRIGGERS = {"trg_broker_master_flags_default", "trg_broker_master_flags_not_null"}
FLAGS = "SELECT broker_id, active_status, enabled_for_new_ingestion FROM broker_master ORDER BY broker_id"


def _triggers(conn) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}


@pytest.fixture(scope="module")
def fresh(tmp_path_factory):
    db = tmp_path_factory.mktemp("fresh_brokers") / "fresh.db"
    alembic(db, "upgrade", "head")
    return db


def test_fresh_upgrade_leaves_no_null_broker_flags(fresh):
    with sqlite3.connect(fresh) as conn:
        rows = conn.execute(FLAGS).fetchall()
        assert rows and all(active == 1 and enabled == 1 for _, active, enabled in rows)
        assert TRIGGERS <= _triggers(conn)


def test_get_brokers_returns_200_on_a_fresh_database(fresh):
    engine = create_engine(f"sqlite:///{fresh}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine)

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    schema_readiness.reset_cache()
    app.dependency_overrides[get_db] = override
    try:
        resp = TestClient(app).get("/api/brokers")
    finally:
        app.dependency_overrides.clear()
        schema_readiness.reset_cache()
        engine.dispose()
    assert resp.status_code == 200
    assert all(b["active_status"] is True and b["enabled_for_new_ingestion"] is True for b in resp.json())


@pytest.fixture
def populated(tmp_path):
    """Seeded NULL flags plus explicit false values, aliases and relationships, then upgraded."""
    db = tmp_path / "populated.db"
    alembic(db, "upgrade", BEFORE_FIX)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO broker_master (canonical_name, normalized_name, display_name, active_status, "
                 "enabled_for_new_ingestion) VALUES ('Synthetic Retired', 'syntheticretired', 'Retired', 0, 0)")
    conn.execute("INSERT INTO broker_master (canonical_name, normalized_name, display_name, active_status, "
                 "enabled_for_new_ingestion) VALUES ('Synthetic Paused', 'syntheticpaused', 'Paused', 1, 0)")
    conn.execute("INSERT INTO broker_alias (broker_id, alias_name) VALUES (1, 'Synthetic Alias One'), (6, 'Synthetic Alias Six')")
    conn.execute("INSERT INTO broker_relationship (predecessor_id, successor_id, relationship_type) VALUES (6, 7, 'RENAMED')")
    conn.commit()
    before = {
        "flags": conn.execute(FLAGS).fetchall(),
        "brokers": conn.execute("SELECT broker_id, canonical_name, normalized_name, display_name FROM broker_master ORDER BY 1").fetchall(),
        "aliases": conn.execute("SELECT * FROM broker_alias ORDER BY 1").fetchall(),
        "relationships": conn.execute("SELECT * FROM broker_relationship ORDER BY 1").fetchall(),
    }
    conn.close()
    alembic(db, "upgrade", "head")
    conn = sqlite3.connect(db)
    yield db, conn, before
    conn.close()


def test_upgrade_backfills_nulls_and_preserves_explicit_false(populated):
    _, conn, before = populated
    assert any(active is None for _, active, _ in before["flags"])  # the seeded brokers really were NULL
    after = dict((bid, (a, e)) for bid, a, e in conn.execute(FLAGS).fetchall())
    for bid, active, enabled in before["flags"]:
        assert after[bid] == (1 if active is None else active, 1 if enabled is None else enabled)
    assert after[6] == (0, 0) and after[7] == (1, 0)


def test_upgrade_preserves_broker_identities_aliases_and_relationships(populated):
    _, conn, before = populated
    assert conn.execute("SELECT broker_id, canonical_name, normalized_name, display_name FROM broker_master ORDER BY 1").fetchall() == before["brokers"]
    assert conn.execute("SELECT * FROM broker_alias ORDER BY 1").fetchall() == before["aliases"]
    assert conn.execute("SELECT * FROM broker_relationship ORDER BY 1").fetchall() == before["relationships"]
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_future_direct_inserts_default_to_true_and_null_updates_are_rejected(populated):
    _, conn, _ = populated
    conn.execute("INSERT INTO broker_master (canonical_name, normalized_name, display_name) VALUES ('Synthetic New', 'syntheticnew', 'New')")
    conn.execute("INSERT INTO broker_master (canonical_name, normalized_name, display_name, active_status) VALUES ('Synthetic Off', 'syntheticoff', 'Off', 0)")
    rows = conn.execute("SELECT canonical_name, active_status, enabled_for_new_ingestion FROM broker_master WHERE canonical_name IN ('Synthetic New', 'Synthetic Off') ORDER BY 1").fetchall()
    assert rows == [("Synthetic New", 1, 1), ("Synthetic Off", 0, 1)]
    for flag in ("active_status", "enabled_for_new_ingestion"):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(f"UPDATE broker_master SET {flag} = NULL WHERE broker_id = 1")
    conn.execute("UPDATE broker_master SET active_status = 0 WHERE broker_id = 1")  # false stays allowed
    assert conn.execute("SELECT active_status FROM broker_master WHERE broker_id = 1").fetchone()[0] == 0


def test_downgrade_drops_triggers_and_keeps_corrected_values(populated):
    db, conn, _ = populated
    corrected = conn.execute(FLAGS).fetchall()
    conn.close()
    alembic(db, "downgrade", BEFORE_FIX)
    with sqlite3.connect(db) as c:
        assert not (TRIGGERS & _triggers(c))
        assert c.execute(FLAGS).fetchall() == corrected  # documented: NULLs are not restored
    alembic(db, "upgrade", "head")
    with sqlite3.connect(db) as c:
        assert TRIGGERS <= _triggers(c)
