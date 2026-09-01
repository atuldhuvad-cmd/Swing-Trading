"""
Test that an Alembic-upgraded database contains the TradeJournal columns
required by the SQLAlchemy model.

This test catches migration drift that Base.metadata.create_all() would mask.
"""
import pytest
import subprocess
import sqlite3
import os
import sys
import shutil
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent.parent
PYTHON_EXECUTABLE = Path(sys.executable)


@pytest.fixture(scope="module")
def migrated_db(tmp_path_factory):
    """Create a fresh database by running Alembic migrations (not create_all)."""
    db_dir = tmp_path_factory.mktemp("migration_test")
    db_path = db_dir / "test_migrated.db"
    db_url = f"sqlite:///{db_path}"

    env = os.environ.copy()
    env["DATABASE_URL"] = db_url

    result = subprocess.run(
        [str(PYTHON_EXECUTABLE), "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        capture_output=True, text=True, env=env
    )
    assert result.returncode == 0, f"Alembic upgrade failed:\n{result.stderr}"

    conn = sqlite3.connect(str(db_path))
    yield conn
    conn.close()


def test_trade_journal_has_entry_price_source(migrated_db):
    """Regression: entry_price_source must exist in the physical schema."""
    cursor = migrated_db.cursor()
    cursor.execute("PRAGMA table_info(trade_journal)")
    columns = [row[1] for row in cursor.fetchall()]
    assert "entry_price_source" in columns, (
        f"entry_price_source missing from trade_journal. Columns: {columns}"
    )


def test_trade_journal_has_exit_price_source(migrated_db):
    """Regression: exit_price_source must exist in the physical schema."""
    cursor = migrated_db.cursor()
    cursor.execute("PRAGMA table_info(trade_journal)")
    columns = [row[1] for row in cursor.fetchall()]
    assert "exit_price_source" in columns, (
        f"exit_price_source missing from trade_journal. Columns: {columns}"
    )


def test_trade_journal_model_columns_match_migration(migrated_db):
    """
    Verify all TradeJournal model columns exist in the migrated schema.
    This catches any future drift between models.py and Alembic migrations.
    """
    # Expected columns from models.py TradeJournal
    expected_columns = {
        "trade_id", "stock_id", "candidate_evaluation_id", "risk_reward_result_id",
        "status", "side", "planned_entry_price", "planned_stop_price",
        "planned_target_price", "quantity", "entry_price", "entry_date",
        "entry_note", "entry_price_source", "exit_price", "exit_date",
        "exit_note", "exit_price_source", "manual_charges", "gross_pnl",
        "net_pnl", "trade_notes", "created_at", "updated_at",
    }

    cursor = migrated_db.cursor()
    cursor.execute("PRAGMA table_info(trade_journal)")
    actual_columns = {row[1] for row in cursor.fetchall()}

    missing = expected_columns - actual_columns
    assert not missing, (
        f"TradeJournal model columns missing from migrated schema: {missing}"
    )
