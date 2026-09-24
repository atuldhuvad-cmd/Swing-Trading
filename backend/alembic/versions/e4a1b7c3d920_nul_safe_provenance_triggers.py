"""Make source_reference provenance triggers NUL-safe

Revision ID: e4a1b7c3d920
Revises: c9d3f6a2e815
Create Date: 2026-09-25 14:00:00.000000

SQLite's length() and GLOB stop at an embedded NUL character, so the
b5e8c2d17a40 triggers accepted a valid-looking prefix followed by
"\\x00/../..." (or a hash followed by "\\x00C:\\..."). These triggers also check
the byte length and reject any NUL:

  document_sha256  NULL, or text of exactly 64 bytes, no NUL, lowercase hex only.
  local_upload_id  NULL, or text of exactly 24 bytes, no NUL, in the form
                   YYYYMMDD_HHMMSS_<8 lowercase hex> ('_' at positions 9 and 16,
                   digits elsewhere before the suffix); this excludes '/', '\\',
                   '..', ':', URI schemes, whitespace and trailing data.

Before replacing the triggers, existing non-NULL values are scanned; any invalid
row aborts the migration (nothing is rewritten). Downgrade restores the
b5e8c2d17a40 trigger definitions.
"""
import re
from typing import Sequence, Union

from alembic import op


revision: str = 'e4a1b7c3d920'
down_revision: Union[str, Sequence[str], None] = 'c9d3f6a2e815'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TRIGGERS = {
    'trg_source_reference_provenance_insert': 'BEFORE INSERT ON source_reference',
    'trg_source_reference_provenance_update': 'BEFORE UPDATE OF document_sha256, local_upload_id ON source_reference',
}
MESSAGE = 'invalid source_reference provenance (document_sha256 / local_upload_id)'

_D, _H = "[0-9]", "[0-9a-f]"


def _sha_invalid(col: str) -> str:
    return f"""(NEW.{col} IS NOT NULL AND (
        typeof(NEW.{col}) != 'text'
        OR length(CAST(NEW.{col} AS BLOB)) != 64
        OR instr(NEW.{col}, char(0)) > 0
        OR NEW.{col} GLOB '*[^0-9a-f]*'))"""


def _upload_invalid(col: str) -> str:
    return f"""(NEW.{col} IS NOT NULL AND (
        typeof(NEW.{col}) != 'text'
        OR length(CAST(NEW.{col} AS BLOB)) != 24
        OR instr(NEW.{col}, char(0)) > 0
        OR substr(NEW.{col}, 9, 1) != '_'
        OR substr(NEW.{col}, 16, 1) != '_'
        OR substr(NEW.{col}, 1, 8) NOT GLOB '{_D * 8}'
        OR substr(NEW.{col}, 10, 6) NOT GLOB '{_D * 6}'
        OR substr(NEW.{col}, 17, 8) NOT GLOB '{_H * 8}'))"""


NUL_SAFE_INVALID = f"{_sha_invalid('document_sha256')} OR {_upload_invalid('local_upload_id')}"

# b5e8c2d17a40 definition, restored on downgrade.
PREVIOUS_INVALID = f"""
    (NEW.document_sha256 IS NOT NULL AND (
        typeof(NEW.document_sha256) != 'text'
        OR length(NEW.document_sha256) != 64
        OR NEW.document_sha256 GLOB '*[^0-9a-f]*'))
    OR (NEW.local_upload_id IS NOT NULL AND (
        typeof(NEW.local_upload_id) != 'text'
        OR length(NEW.local_upload_id) != 24
        OR NEW.local_upload_id NOT GLOB '{_D * 8 + "_" + _D * 6 + "_" + _H * 8}'))
"""

_SHA_RE = re.compile(r"[0-9a-f]{64}")
_UPLOAD_RE = re.compile(r"[0-9]{8}_[0-9]{6}_[0-9a-f]{8}")


def _valid(value, pattern) -> bool:
    return isinstance(value, str) and value.isascii() and "\x00" not in value and pattern.fullmatch(value) is not None


def _install(condition: str) -> None:
    for name, event in TRIGGERS.items():
        op.execute(f"DROP TRIGGER IF EXISTS {name}")
        op.execute(f"""
            CREATE TRIGGER {name} {event}
            FOR EACH ROW WHEN {condition}
            BEGIN
                SELECT RAISE(ABORT, '{MESSAGE}');
            END
        """)


def upgrade() -> None:
    rows = op.get_bind().exec_driver_sql(
        "SELECT source_reference_id, document_sha256, local_upload_id FROM source_reference "
        "WHERE document_sha256 IS NOT NULL OR local_upload_id IS NOT NULL").fetchall()
    bad = [rid for rid, sha, upload in rows
           if (sha is not None and not _valid(sha, _SHA_RE)) or (upload is not None and not _valid(upload, _UPLOAD_RE))]
    if bad:
        shown = ", ".join(map(str, bad[:20])) + (" ..." if len(bad) > 20 else "")
        raise RuntimeError(f"{len(bad)} source_reference row(s) have invalid provenance (ids {shown}); "
                           "correct them before upgrading. Nothing was changed.")
    _install(NUL_SAFE_INVALID)


def downgrade() -> None:
    _install(PREVIOUS_INVALID)
