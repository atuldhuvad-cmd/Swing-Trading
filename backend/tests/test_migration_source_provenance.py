"""Upgrade an existing database to the source_reference PDF provenance revision.

Uses a temporary database only. Existing rows must survive unchanged with NULL provenance.
"""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
PREVIOUS_HEAD = "a1b2c3d4e5f6"
REVISION = "f2a7c9d41b3e"


def _alembic(db_path: Path, *args: str) -> None:
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{db_path}")
    result = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=str(BACKEND_DIR),
                            capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr


def _columns(conn) -> list[str]:
    return [r[1] for r in conn.execute("PRAGMA table_info(source_reference)")]


@pytest.fixture(scope="module")
def upgraded(tmp_path_factory):
    db = tmp_path_factory.mktemp("provenance_migration") / "existing.db"
    _alembic(db, "upgrade", PREVIOUS_HEAD)
    conn = sqlite3.connect(db)
    type_id = conn.execute("SELECT source_type_id FROM source_type_master ORDER BY source_type_id LIMIT 1").fetchone()
    if type_id is None:
        conn.execute("INSERT INTO source_type_master (type_name) VALUES ('BROKER_RESEARCH')")
        type_id = conn.execute("SELECT last_insert_rowid()").fetchone()
    conn.execute(
        "INSERT INTO source_reference (source_type_id, publication_name, url, verification_status, original_text) "
        "VALUES (?, 'Synthetic Broker', 'https://example.invalid/report.pdf', 'VERIFIED_PRIMARY', 'synthetic extract')",
        (type_id[0],))
    conn.commit()
    before = conn.execute("SELECT * FROM source_reference").fetchall()
    before_cols = _columns(conn)
    conn.close()
    _alembic(db, "upgrade", "head")
    conn = sqlite3.connect(db)
    yield db, conn, before, before_cols
    conn.close()


def test_upgrade_adds_nullable_provenance_columns_and_index(upgraded):
    _, conn, _, before_cols = upgraded
    assert "document_sha256" not in before_cols and "local_upload_id" not in before_cols
    info = {r[1]: r for r in conn.execute("PRAGMA table_info(source_reference)")}
    assert info["document_sha256"][3] == 0 and info["local_upload_id"][3] == 0  # nullable
    assert "ix_source_reference_document_sha256" in {r[1] for r in conn.execute("PRAGMA index_list(source_reference)")}
    assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == REVISION


def test_upgrade_preserves_existing_rows_without_inferring_hashes(upgraded):
    _, conn, before, before_cols = upgraded
    rows = conn.execute(f"SELECT {', '.join(before_cols)}, document_sha256, local_upload_id FROM source_reference").fetchall()
    assert [r[:len(before_cols)] for r in rows] == before
    assert all(r[-2] is None and r[-1] is None for r in rows)
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_downgrade_then_upgrade_round_trip(tmp_path):
    db = tmp_path / "roundtrip.db"
    _alembic(db, "upgrade", "head")
    _alembic(db, "downgrade", PREVIOUS_HEAD)
    conn = sqlite3.connect(db)
    assert "document_sha256" not in _columns(conn)
    conn.close()
    _alembic(db, "upgrade", "head")
    conn = sqlite3.connect(db)
    assert {"document_sha256", "local_upload_id"} <= set(_columns(conn))
    conn.close()


def test_model_validates_provenance_format():
    from app.models import SourceReference

    ok = SourceReference(document_sha256="a" * 64, local_upload_id="20260903_203319_1efbd821")
    assert ok.document_sha256 == "a" * 64
    for bad in ("A" * 64, "a" * 63, "g" * 64, "../" + "a" * 61):
        with pytest.raises(ValueError):
            SourceReference(document_sha256=bad)
    for bad in ("uploads/icici/report.pdf", "C:\\\\reports\\\\x.pdf", "20260903_203319_1EFBD821"):
        with pytest.raises(ValueError):
            SourceReference(local_upload_id=bad)
