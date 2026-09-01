"""feat_add_fundamental_snapshot_provenance

Revision ID: c3e91f4a7b2d
Revises: 6291b9bcaaa3
Create Date: 2026-08-16 07:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3e91f4a7b2d"
down_revision: Union[str, Sequence[str], None] = "6291b9bcaaa3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite ADD COLUMN avoids table rebuild / FK drop of fundamental_snapshot.
    op.execute("ALTER TABLE fundamental_snapshot ADD COLUMN statement_scope VARCHAR(20)")
    op.execute("ALTER TABLE fundamental_snapshot ADD COLUMN source_line_item VARCHAR(100)")
    op.execute("ALTER TABLE fundamental_snapshot ADD COLUMN original_unit VARCHAR(30)")


def downgrade() -> None:
    op.execute("ALTER TABLE fundamental_snapshot DROP COLUMN original_unit")
    op.execute("ALTER TABLE fundamental_snapshot DROP COLUMN source_line_item")
    op.execute("ALTER TABLE fundamental_snapshot DROP COLUMN statement_scope")
