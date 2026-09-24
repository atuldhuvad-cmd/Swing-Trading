"""Add PDF document provenance to source_reference

Revision ID: f2a7c9d41b3e
Revises: a1b2c3d4e5f6
Create Date: 2026-09-24 21:00:00.000000

Adds two nullable columns and an index. Existing rows are kept unchanged with
NULL provenance: historical document hashes are never inferred.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2a7c9d41b3e'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX = 'ix_source_reference_document_sha256'


def _columns() -> set[str]:
    bind = op.get_bind()
    return {row[1] for row in bind.execute(sa.text("PRAGMA table_info(source_reference)"))}


def _indexes() -> set[str]:
    bind = op.get_bind()
    return {row[1] for row in bind.execute(sa.text("PRAGMA index_list(source_reference)"))}


def upgrade() -> None:
    # Plain ADD COLUMN (no table rebuild), so existing rows and foreign keys are untouched.
    cols = _columns()
    if 'document_sha256' not in cols:
        op.add_column('source_reference', sa.Column('document_sha256', sa.String(length=64), nullable=True))
    if 'local_upload_id' not in cols:
        op.add_column('source_reference', sa.Column('local_upload_id', sa.String(length=64), nullable=True))
    if INDEX not in _indexes():
        op.create_index(INDEX, 'source_reference', ['document_sha256'])


def downgrade() -> None:
    if INDEX in _indexes():
        op.drop_index(INDEX, table_name='source_reference')
    cols = _columns()
    if 'local_upload_id' in cols:
        op.drop_column('source_reference', 'local_upload_id')
    if 'document_sha256' in cols:
        op.drop_column('source_reference', 'document_sha256')
