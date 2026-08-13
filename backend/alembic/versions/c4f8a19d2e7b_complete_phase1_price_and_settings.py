"""Complete Phase 1 price cache and settings.

Revision ID: c4f8a19d2e7b
Revises: a8c967a3411d
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c4f8a19d2e7b'
down_revision: Union[str, Sequence[str], None] = 'a8c967a3411d'
branch_labels = None
depends_on = None

def upgrade() -> None:
    with op.batch_alter_table('stock_price') as batch_op:
        batch_op.add_column(sa.Column('previous_price', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('price_change', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('percentage_change', sa.Float(), nullable=True))
    op.execute("INSERT OR IGNORE INTO system_setting (setting_key, setting_value, description) VALUES ('UNIVERSE_MAX_AGE_DAYS', '30', 'Maximum recommendation age in default candidate universe')")
    op.execute("INSERT OR IGNORE INTO system_setting (setting_key, setting_value, description) VALUES ('ELIGIBLE_BULLISH_RATINGS', 'BUY,STRONG_BUY,ACCUMULATE,ADD,OUTPERFORM,POSITIVE', 'Normalized ratings eligible for bullish consensus')")

def downgrade() -> None:
    op.execute("DELETE FROM system_setting WHERE setting_key IN ('UNIVERSE_MAX_AGE_DAYS', 'ELIGIBLE_BULLISH_RATINGS')")
    with op.batch_alter_table('stock_price') as batch_op:
        batch_op.drop_column('percentage_change')
        batch_op.drop_column('price_change')
        batch_op.drop_column('previous_price')
