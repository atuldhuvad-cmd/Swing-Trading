"""Backfill NULL broker_master flags and default them for future inserts

Revision ID: c9d3f6a2e815
Revises: b5e8c2d17a40
Create Date: 2026-09-25 10:05:00.000000

The initial migration seeded brokers without active_status /
enabled_for_new_ingestion, leaving them NULL (the model's default=True applies
only to ORM inserts). Decision: those seeded brokers are active and enabled.

  * NULL flags become 1; an explicit 0 (false) is preserved.
  * SQLite cannot add a column DEFAULT or NOT NULL without rebuilding
    broker_master, which many tables reference, so triggers provide both:
    an AFTER INSERT trigger turns a NULL flag into 1 (the database default for
    direct SQL inserts), and a BEFORE UPDATE trigger rejects setting a flag to NULL.
  * No broker row, id, alias or relationship is added, removed or re-keyed.

Downgrade drops the triggers only. The backfilled values stay 1: that is the
intended state, and which rows were NULL is not recorded, so NULLs are not restored.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c9d3f6a2e815'
down_revision: Union[str, Sequence[str], None] = 'b5e8c2d17a40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FLAGS = ("active_status", "enabled_for_new_ingestion")
TRIGGERS = ("trg_broker_master_flags_default", "trg_broker_master_flags_not_null")


def upgrade() -> None:
    for flag in FLAGS:
        op.execute(f"UPDATE broker_master SET {flag} = 1 WHERE {flag} IS NULL")
    for name in TRIGGERS:
        op.execute(f"DROP TRIGGER IF EXISTS {name}")
    op.execute("""
        CREATE TRIGGER trg_broker_master_flags_default AFTER INSERT ON broker_master
        FOR EACH ROW WHEN NEW.active_status IS NULL OR NEW.enabled_for_new_ingestion IS NULL
        BEGIN
            UPDATE broker_master
               SET active_status = COALESCE(NEW.active_status, 1),
                   enabled_for_new_ingestion = COALESCE(NEW.enabled_for_new_ingestion, 1)
             WHERE broker_id = NEW.broker_id;
        END
    """)
    op.execute("""
        CREATE TRIGGER trg_broker_master_flags_not_null
        BEFORE UPDATE OF active_status, enabled_for_new_ingestion ON broker_master
        FOR EACH ROW WHEN NEW.active_status IS NULL OR NEW.enabled_for_new_ingestion IS NULL
        BEGIN
            SELECT RAISE(ABORT, 'broker_master flags cannot be NULL');
        END
    """)


def downgrade() -> None:
    for name in TRIGGERS:
        op.execute(f"DROP TRIGGER IF EXISTS {name}")
