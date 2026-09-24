"""Database schema readiness: is the database at the repository's Alembic head?

The check is read-only (it only queries ``sqlite_master`` and ``alembic_version``)
and never migrates anything. API routes refuse service with a controlled 503
until the schema is current; ``/health`` reports the state; scheduled scripts
that write production data call ``write_refusal`` before touching the database.
"""
from __future__ import annotations

import functools
import logging
from dataclasses import dataclass
from pathlib import Path

from fastapi import Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .database import get_db

BACKEND_DIR = Path(__file__).resolve().parent.parent
MIGRATION_INSTRUCTION = (
    "Database schema is not current. Back up the database (SQLite backup API), "
    "then run 'alembic upgrade head' from the backend folder."
)

CURRENT, MISSING, BEHIND, UNEXPECTED, UNAVAILABLE = "CURRENT", "MISSING", "BEHIND", "UNEXPECTED", "UNAVAILABLE"

log = logging.getLogger("uvicorn.error")


@functools.lru_cache(maxsize=1)
def _script_revisions() -> tuple[str, frozenset[str]]:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"Expected one Alembic head, found {len(heads)}")
    return heads[0], frozenset(rev.revision for rev in script.walk_revisions())


def expected_head() -> str:
    return _script_revisions()[0]


@dataclass(frozen=True)
class SchemaStatus:
    state: str
    database_revision: str | None
    expected_revision: str

    @property
    def ok(self) -> bool:
        return self.state == CURRENT

    def public(self) -> dict:
        """Client-safe summary: revision ids only, never SQL, paths or exception text."""
        return {"state": self.state, "database_revision": self.database_revision,
                "expected_revision": self.expected_revision}


def check_schema(connection) -> SchemaStatus:
    """Read-only comparison of the database revision with the repository head."""
    head, known = _script_revisions()
    try:
        has_table = connection.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'alembic_version'").first()
        if not has_table:
            return SchemaStatus(MISSING, None, head)
        rows = [r[0] for r in connection.exec_driver_sql("SELECT version_num FROM alembic_version").fetchall()]
    except SQLAlchemyError:
        return SchemaStatus(UNAVAILABLE, None, head)
    if not rows:
        return SchemaStatus(MISSING, None, head)
    if len(rows) > 1:
        return SchemaStatus(UNEXPECTED, ",".join(sorted(rows)), head)
    revision = rows[0]
    if revision == head:
        return SchemaStatus(CURRENT, revision, head)
    return SchemaStatus(BEHIND if revision in known else UNEXPECTED, revision, head)


_current_databases: set[str] = set()


def reset_cache() -> None:
    _current_databases.clear()


def require_current_schema(db: Session = Depends(get_db)) -> None:
    """Router dependency: controlled 503 until the database is at the Alembic head."""
    key = str(db.get_bind().url)
    if key in _current_databases:
        return
    try:
        status = check_schema(db.connection())
    except SQLAlchemyError:
        status = SchemaStatus(UNAVAILABLE, None, expected_head())
    if status.ok:
        _current_databases.add(key)  # a current database stays current while the app runs
        return
    raise HTTPException(status_code=503, detail={"error": "SCHEMA_NOT_CURRENT", **status.public(),
                                                 "action": MIGRATION_INSTRUCTION})


def write_refusal(session_factory) -> str | None:
    """For scripts that write production data: a refusal message, or None when current."""
    session = session_factory()
    try:
        status = check_schema(session.connection())
    except SQLAlchemyError:
        status = SchemaStatus(UNAVAILABLE, None, expected_head())
    finally:
        session.close()
    if status.ok:
        return None
    return (f"REFUSED: database schema is {status.state} (database {status.database_revision or 'none'}, "
            f"expected {status.expected_revision}). {MIGRATION_INSTRUCTION} No database write was attempted.")


def log_startup_status(engine) -> None:
    """Concise startup message; never raises and never migrates."""
    try:
        with engine.connect() as conn:
            status = check_schema(conn)
    except Exception:  # noqa: BLE001 - startup must not fail on a diagnostic
        log.warning("Database schema check could not run. %s", MIGRATION_INSTRUCTION)
        return
    if status.ok:
        log.info("Database schema is current (%s).", status.expected_revision)
    else:
        log.warning("Database schema is %s (database %s, expected %s). API routes will return 503. %s",
                    status.state, status.database_revision or "none", status.expected_revision,
                    MIGRATION_INSTRUCTION)
