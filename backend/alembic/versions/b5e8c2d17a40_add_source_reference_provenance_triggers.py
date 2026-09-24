"""Enforce source_reference PDF provenance formats in the database

Revision ID: b5e8c2d17a40
Revises: f2a7c9d41b3e
Create Date: 2026-09-25 10:00:00.000000

SQLite cannot add CHECK constraints without rebuilding the table, so BEFORE
INSERT / BEFORE UPDATE triggers reject malformed values instead. They apply to
every writer (ORM, bulk update, direct SQL). NULL stays allowed; existing rows
are not changed and no historical provenance is inferred.

  document_sha256  NULL or exactly 64 lowercase hex characters (text).
  local_upload_id  NULL or an upload id: YYYYMMDD_HHMMSS_<8 lowercase hex>
                   (24 characters), so a path, drive, URI or filename can never
                   be stored.

Downgrade drops only the triggers; data is untouched.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'b5e8c2d17a40'
down_revision: Union[str, Sequence[str], None] = 'f2a7c9d41b3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_D = "[0-9]"
_H = "[0-9a-f]"
UPLOAD_ID_GLOB = _D * 8 + "_" + _D * 6 + "_" + _H * 8

INVALID = f"""
    (NEW.document_sha256 IS NOT NULL AND (
        typeof(NEW.document_sha256) != 'text'
        OR length(NEW.document_sha256) != 64
        OR NEW.document_sha256 GLOB '*[^0-9a-f]*'))
    OR (NEW.local_upload_id IS NOT NULL AND (
        typeof(NEW.local_upload_id) != 'text'
        OR length(NEW.local_upload_id) != 24
        OR NEW.local_upload_id NOT GLOB '{UPLOAD_ID_GLOB}'))
"""

TRIGGERS = {
    'trg_source_reference_provenance_insert': 'BEFORE INSERT ON source_reference',
    'trg_source_reference_provenance_update': 'BEFORE UPDATE OF document_sha256, local_upload_id ON source_reference',
}


def upgrade() -> None:
    for name, event in TRIGGERS.items():
        op.execute(f"DROP TRIGGER IF EXISTS {name}")
        op.execute(f"""
            CREATE TRIGGER {name} {event}
            FOR EACH ROW WHEN {INVALID}
            BEGIN
                SELECT RAISE(ABORT, 'invalid source_reference provenance (document_sha256 / local_upload_id)');
            END
        """)


def downgrade() -> None:
    for name in TRIGGERS:
        op.execute(f"DROP TRIGGER IF EXISTS {name}")
