"""Database-level enforcement of source_reference PDF provenance (migration b5e8c2d17a40).

Disposable databases only; values are synthetic.
"""
import shutil
import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models import SourceReference
from tests.migration_helpers import alembic

PREVIOUS = "f2a7c9d41b3e"
TRIGGERS = {"trg_source_reference_provenance_insert", "trg_source_reference_provenance_update"}
VALID_SHA = "0123456789abcdef" * 4
VALID_UPLOAD = "20260903_203319_1efbd821"
BAD_SHA = ["A" * 64, "a" * 63, "a" * 65, "g" * 64, " " + "a" * 63, "a" * 63 + " ", "a" * 63 + "\n", ""]
BAD_UPLOAD = ["uploads/icici/r.pdf", "..\\r.pdf", "C:\\reports\\r.pdf", "C:20260903_203319_1efbd8",
              "file:///tmp/r.pdf", "20260903_203319_1efbd82 ", "20260903_203319_1EFBD821",
              "20260903_203319_1efbd821.pdf", "20260903/203319_1efbd821", "../20260903_203319_1efbd8",
              "report.pdf", "", " 20260903_203319_1efbd82"]


def _triggers(conn) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    """A populated database at the previous revision, then upgraded to head (built once)."""
    db = tmp_path_factory.mktemp("provenance") / "template.db"
    alembic(db, "upgrade", PREVIOUS)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO stock_master (nse_symbol, company_name, listing_status) VALUES ('SYNTH', 'Synthetic Co', 'ACTIVE')")
    conn.execute("INSERT INTO broker_recommendation (stock_id, broker_id, recommendation_date, original_rating, "
                 "normalized_rating, lifecycle_status, currency) VALUES (1, 1, '2026-09-01', 'BUY', 'BUY', 'CURRENT', 'INR')")
    conn.execute("INSERT INTO source_reference (source_type_id, publication_name, verification_status) "
                 "VALUES (1, 'Synthetic Broker', 'VERIFIED_PRIMARY')")
    conn.execute("INSERT INTO source_reference (source_type_id, publication_name, verification_status, "
                 "document_sha256, local_upload_id) VALUES (1, 'Synthetic Broker', 'VERIFIED_PRIMARY', ?, ?)",
                 (VALID_SHA, VALID_UPLOAD))
    conn.execute("INSERT INTO recommendation_source (recommendation_id, source_reference_id) VALUES (1, 1), (1, 2)")
    conn.commit()
    before = (conn.execute("SELECT * FROM source_reference ORDER BY 1").fetchall(),
              conn.execute("SELECT * FROM recommendation_source ORDER BY 1").fetchall())
    conn.close()
    alembic(db, "upgrade", "head")
    return db, before


@pytest.fixture
def migrated(template, tmp_path):
    """A private copy of the template for each test."""
    db = tmp_path / "provenance.db"
    shutil.copyfile(template[0], db)
    conn = sqlite3.connect(db)
    yield db, conn, template[1]
    conn.close()


def test_upgrade_creates_triggers_and_preserves_rows(migrated):
    _, conn, before = migrated
    assert TRIGGERS <= _triggers(conn)
    assert conn.execute("SELECT * FROM source_reference ORDER BY 1").fetchall() == before[0]
    assert conn.execute("SELECT * FROM recommendation_source ORDER BY 1").fetchall() == before[1]
    assert conn.execute("SELECT document_sha256, local_upload_id FROM source_reference WHERE source_reference_id = 1").fetchone() == (None, None)
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("bad", BAD_SHA)
def test_direct_sql_rejects_malformed_sha(migrated, bad):
    _, conn, _ = migrated
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO source_reference (source_type_id, verification_status, document_sha256) "
                     "VALUES (1, 'PROVISIONAL', ?)", (bad,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE source_reference SET document_sha256 = ? WHERE source_reference_id = 1", (bad,))


@pytest.mark.parametrize("bad", BAD_UPLOAD)
def test_direct_sql_rejects_path_like_upload_id(migrated, bad):
    _, conn, _ = migrated
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO source_reference (source_type_id, verification_status, local_upload_id) "
                     "VALUES (1, 'PROVISIONAL', ?)", (bad,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE source_reference SET local_upload_id = ? WHERE source_reference_id = 1", (bad,))


def test_non_text_values_are_rejected(migrated):
    _, conn, _ = migrated
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE source_reference SET document_sha256 = ? WHERE source_reference_id = 1", (b"a" * 64,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE source_reference SET local_upload_id = 20260903203319 WHERE source_reference_id = 1")


def test_valid_and_null_values_are_accepted(migrated):
    _, conn, _ = migrated
    conn.execute("INSERT INTO source_reference (source_type_id, verification_status, document_sha256, local_upload_id) "
                 "VALUES (1, 'PROVISIONAL', ?, ?)", ("f" * 64, "20261231_235959_00ff00ff"))
    conn.execute("INSERT INTO source_reference (source_type_id, verification_status) VALUES (1, 'PROVISIONAL')")
    conn.execute("UPDATE source_reference SET document_sha256 = NULL, local_upload_id = NULL WHERE source_reference_id = 2")
    conn.execute("UPDATE source_reference SET publication_name = 'Renamed' WHERE source_reference_id = 1")
    conn.commit()
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_orm_bulk_update_cannot_bypass_the_database(migrated):
    db, _, _ = migrated
    engine = create_engine(f"sqlite:///{db}")
    session = sessionmaker(bind=engine)()
    try:
        with pytest.raises(IntegrityError):
            session.query(SourceReference).update({"local_upload_id": "uploads/x/../../r.pdf"})
        session.rollback()
        with pytest.raises(IntegrityError):
            session.query(SourceReference).update({"document_sha256": "XYZ"})
        session.rollback()
        assert session.query(SourceReference.local_upload_id).filter_by(source_reference_id=2).scalar() == VALID_UPLOAD
    finally:
        session.close()
        engine.dispose()


def test_downgrade_drops_only_the_triggers_and_upgrade_restores_them(migrated):
    db, conn, before = migrated
    conn.close()
    alembic(db, "downgrade", PREVIOUS)
    conn = sqlite3.connect(db)
    assert not (TRIGGERS & _triggers(conn))
    assert conn.execute("SELECT * FROM source_reference ORDER BY 1").fetchall() == before[0]
    conn.close()
    alembic(db, "upgrade", "head")
    conn = sqlite3.connect(db)
    assert TRIGGERS <= _triggers(conn)
    conn.close()


def test_api_returns_upload_id_but_no_filesystem_path(migrated, monkeypatch):
    from fastapi.testclient import TestClient

    from app import schema_readiness
    from app.database import get_db
    from app.main import app

    db, _, _ = migrated
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
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
        body = TestClient(app).get("/api/recommendations/1").json()
    finally:
        app.dependency_overrides.clear()
        schema_readiness.reset_cache()
        engine.dispose()
    linked = [s for s in body["sources"] if s["document_sha256"]]
    assert linked and linked[0]["local_upload_id"] == VALID_UPLOAD
    text = str(body)
    assert "stored_path" not in text and "manual_inputs" not in text and "/uploads/" not in text
