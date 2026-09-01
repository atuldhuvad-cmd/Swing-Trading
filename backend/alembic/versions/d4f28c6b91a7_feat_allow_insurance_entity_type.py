"""feat_allow_insurance_entity_type

Widens fundamental_snapshot.entity_type to accept INSURANCE. SQLite cannot alter
a CHECK constraint in place, so the table is rebuilt and rows are copied.

Revision ID: d4f28c6b91a7
Revises: c3e91f4a7b2d
Create Date: 2026-08-16 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "d4f28c6b91a7"
down_revision: Union[str, Sequence[str], None] = "c3e91f4a7b2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = """snapshot_id, stock_id, as_of_date, financial_period, period_type,
             source_reference_id, captured_at, version, is_superseded,
             superseded_by_id, entity_type, statement_scope, source_line_item,
             original_unit"""


def _rebuild(entity_values: str) -> None:
    op.execute("PRAGMA foreign_keys=OFF")
    op.execute(f"""
        CREATE TABLE fundamental_snapshot_new (
            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id INTEGER NOT NULL REFERENCES stock_master(stock_id),
            as_of_date DATE NOT NULL,
            financial_period VARCHAR(50),
            period_type VARCHAR(50),
            source_reference_id INTEGER REFERENCES source_reference(source_reference_id),
            captured_at DATETIME NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            is_superseded BOOLEAN NOT NULL DEFAULT 0,
            superseded_by_id INTEGER REFERENCES fundamental_snapshot(snapshot_id),
            entity_type VARCHAR(50) NOT NULL DEFAULT 'ORDINARY',
            statement_scope VARCHAR(20),
            source_line_item VARCHAR(100),
            original_unit VARCHAR(30),
            CHECK (entity_type IN ({entity_values}))
        )
    """)
    op.execute(
        f"INSERT INTO fundamental_snapshot_new ({COLUMNS}) "
        f"SELECT {COLUMNS} FROM fundamental_snapshot"
    )
    op.execute("DROP TABLE fundamental_snapshot")
    op.execute("ALTER TABLE fundamental_snapshot_new RENAME TO fundamental_snapshot")
    op.execute("PRAGMA foreign_keys=ON")


def upgrade() -> None:
    _rebuild("'ORDINARY','BANK','NBFC','INSURANCE'")


def downgrade() -> None:
    # Refuse to narrow the constraint while INSURANCE evidence exists.
    conn = op.get_bind()
    remaining = conn.exec_driver_sql(
        "SELECT COUNT(*) FROM fundamental_snapshot WHERE entity_type = 'INSURANCE'"
    ).scalar()
    if remaining:
        raise RuntimeError(
            f"{remaining} INSURANCE snapshot(s) exist; migrate or remove them before downgrade"
        )
    _rebuild("'ORDINARY','BANK','NBFC'")
