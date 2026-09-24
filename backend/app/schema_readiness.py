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
ALEMBIC_DIR = BACKEND_DIR / "alembic"
MIGRATION_INSTRUCTION = (
    "Database schema is not current. Back up the database (SQLite backup API), "
    "then run 'alembic upgrade head' from the backend folder."
)

CURRENT, MISSING, BEHIND, UNEXPECTED, UNAVAILABLE = "CURRENT", "MISSING", "BEHIND", "UNEXPECTED", "UNAVAILABLE"

log = logging.getLogger("uvicorn.error")


MULTIPLE_HEADS_INSTRUCTION = (
    "The repository's Alembic migrations have more than one head; the code checkout is "
    "inconsistent. Do not migrate; restore a consistent checkout.")


@functools.lru_cache(maxsize=1)
def _script_revisions() -> tuple[str | None, frozenset[str]]:
    """(the single head, all known revisions); the head is None if there is not exactly one."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    known = frozenset(rev.revision for rev in script.walk_revisions())
    return (heads[0] if len(heads) == 1 else None), known


def expected_head() -> str | None:
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

    @property
    def instruction(self) -> str:
        return MULTIPLE_HEADS_INSTRUCTION if self.expected_revision is None else MIGRATION_INSTRUCTION


def check_schema(connection) -> SchemaStatus:
    """Read-only comparison of the database revision with the repository head."""
    if expected_head() is None:  # multiple heads: never CURRENT, and the database is not queried
        return SchemaStatus(UNEXPECTED, None, None)
    try:
        return _evaluate(lambda sql: connection.exec_driver_sql(sql).fetchall())
    except SQLAlchemyError:
        return SchemaStatus(UNAVAILABLE, None, expected_head())


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
                                                 "action": status.instruction})


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
    return refusal_message(status)


def refusal_message(status: SchemaStatus) -> str:
    """One line for script output: revision ids only, no SQL or paths."""
    return (f"REFUSED: database schema is {status.state} (database {status.database_revision or 'none'}, "
            f"expected {status.expected_revision or 'a single Alembic head'}). {status.instruction} "
            "No backup, download or database write was attempted.")


def _evaluate(execute) -> SchemaStatus:
    head, known = _script_revisions()
    if head is None:
        return SchemaStatus(UNEXPECTED, None, None)
    if not execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'alembic_version'"):
        return SchemaStatus(MISSING, None, head)
    rows = [r[0] for r in execute("SELECT version_num FROM alembic_version")]
    if not rows:
        return SchemaStatus(MISSING, None, head)
    if len(rows) > 1:
        return SchemaStatus(UNEXPECTED, ",".join(sorted(rows)), head)
    if rows[0] == head:
        return SchemaStatus(CURRENT, rows[0], head)
    return SchemaStatus(BEHIND if rows[0] in known else UNEXPECTED, rows[0], head)


def check_database_file(path) -> SchemaStatus:
    """Read-only check of a SQLite file (opened with mode=ro; a missing file is never created)."""
    import sqlite3
    from contextlib import closing

    head = expected_head()
    target = Path(path)
    if not target.is_file():
        return SchemaStatus(MISSING, None, head)
    try:
        with closing(sqlite3.connect(f"{target.resolve().as_uri()}?mode=ro", uri=True)) as conn:
            return _evaluate(lambda sql: conn.execute(sql).fetchall())
    except sqlite3.Error:
        return SchemaStatus(UNAVAILABLE, None, head)


def guard_script_write(target) -> None:
    """Shared guard for scripts that write a database; call it before any backup,
    download or write. ``target`` is the SQLite file the script writes, or a
    session factory / engine for the database it writes. Exits with code 3 unless
    that database is at the Alembic head. Never stamps or migrates anything."""
    if isinstance(target, (str, Path)):
        status = check_database_file(target)
    elif hasattr(target, "connect") and hasattr(target, "dispose"):  # an Engine
        try:
            with target.connect() as conn:
                status = check_schema(conn)
        except SQLAlchemyError:
            status = SchemaStatus(UNAVAILABLE, None, expected_head())
    else:
        message = write_refusal(target)
        if message:
            print(message)
            raise SystemExit(3)
        return
    if not status.ok:
        print(refusal_message(status))
        raise SystemExit(3)


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
                    status.state, status.database_revision or "none", status.expected_revision or "one head",
                    status.instruction)
