"""Add trade provenance columns

Revision ID: a1b2c3d4e5f6
Revises: cb843083b496
Create Date: 2026-08-20 15:49:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'cb843083b496'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    """Return True if *column* already exists in *table* (SQLite safe)."""
    bind = op.get_bind()
    result = bind.execute(sa.text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result)


def upgrade() -> None:
    # Guard: cb843083b496 already created these columns in the initial table
    # definition.  Earlier databases that were created without them need the
    # ALTER TABLE; databases migrated from the initial revision do not.
    if not _column_exists('trade_journal', 'entry_price_source'):
        op.add_column('trade_journal', sa.Column('entry_price_source', sa.String(length=100), nullable=True))
    if not _column_exists('trade_journal', 'exit_price_source'):
        op.add_column('trade_journal', sa.Column('exit_price_source', sa.String(length=100), nullable=True))


def downgrade() -> None:
    # SQLite does not support DROP COLUMN in all versions.
    # For SQLite >= 3.35.0 (2021-03-12) this works directly.
    # The project uses ALTER TABLE via Alembic batch mode if needed,
    # but since these are nullable columns with no constraints,
    # direct drop is the simplest approach.
    if _column_exists('trade_journal', 'exit_price_source'):
        op.drop_column('trade_journal', 'exit_price_source')
    if _column_exists('trade_journal', 'entry_price_source'):
        op.drop_column('trade_journal', 'entry_price_source')
