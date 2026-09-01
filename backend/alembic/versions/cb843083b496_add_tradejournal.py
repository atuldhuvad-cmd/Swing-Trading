'''Add TradeJournal

Revision ID: cb843083b496
Revises: d4f28c6b91a7
Create Date: 2026-08-19 20:38:29.516387

'''
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'cb843083b496'
down_revision: Union[str, Sequence[str], None] = 'd4f28c6b91a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table('trade_journal',
    sa.Column('trade_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('stock_id', sa.Integer(), nullable=False),
    sa.Column('candidate_evaluation_id', sa.Integer(), nullable=True),
    sa.Column('risk_reward_result_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('side', sa.String(length=20), nullable=False),
    sa.Column('planned_entry_price', sa.Numeric(precision=20, scale=4), nullable=True),
    sa.Column('planned_stop_price', sa.Numeric(precision=20, scale=4), nullable=True),
    sa.Column('planned_target_price', sa.Numeric(precision=20, scale=4), nullable=True),
    sa.Column('quantity', sa.Integer(), nullable=True),
    sa.Column('entry_price', sa.Numeric(precision=20, scale=4), nullable=True),
    sa.Column('entry_date', sa.DateTime(), nullable=True),
    sa.Column('entry_note', sa.Text(), nullable=True),
    sa.Column('entry_price_source', sa.String(length=100), nullable=True),
    sa.Column('exit_price', sa.Numeric(precision=20, scale=4), nullable=True),
    sa.Column('exit_date', sa.DateTime(), nullable=True),
    sa.Column('exit_note', sa.Text(), nullable=True),
    sa.Column('exit_price_source', sa.String(length=100), nullable=True),
    sa.Column('manual_charges', sa.Numeric(precision=20, scale=4), nullable=True),
    sa.Column('gross_pnl', sa.Numeric(precision=20, scale=4), nullable=True),
    sa.Column('net_pnl', sa.Numeric(precision=20, scale=4), nullable=True),
    sa.Column('trade_notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint('status IN ("PLANNED", "OPEN", "CLOSED", "CANCELLED")', name='check_trade_status'),
    sa.ForeignKeyConstraint(['candidate_evaluation_id'], ['candidate_evaluation_run.evaluation_id'], ),
    sa.ForeignKeyConstraint(['risk_reward_result_id'], ['risk_reward_result.result_id'], ),
    sa.ForeignKeyConstraint(['stock_id'], ['stock_master.stock_id'], ),
    sa.PrimaryKeyConstraint('trade_id')
    )

def downgrade() -> None:
    op.drop_table('trade_journal')
