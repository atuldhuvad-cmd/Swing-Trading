"""Test helper: mark a create_all() test database as being at the Alembic head.

Test databases are built from the models (Base.metadata.create_all), which match
the head schema; recording the head lets the schema-readiness guard pass.
"""
from sqlalchemy import text

from app import schema_readiness


def stamp_head(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
        conn.execute(text("DELETE FROM alembic_version"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES (:v)"), {"v": schema_readiness.expected_head()})
    schema_readiness.reset_cache()
