"""add logs table

Append-only table with every action done by the API (requests, database
changes and external calls), kept to track errors later.

Revision ID: 35867345c126
Revises: 91bcf7cc5bf7
Create Date: 2026-10-28 01:50:27.549021

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '35867345c126'
down_revision: Union[str, None] = '91bcf7cc5bf7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('logs',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.Column('request_id', sa.Uuid(), nullable=True),
    sa.Column('action', sa.Text(), nullable=False),
    sa.Column('target', sa.Text(), nullable=False),
    sa.Column('record_id', sa.Uuid(), nullable=True),
    sa.Column('operation', sa.Text(), nullable=True),
    sa.Column('user_id', sa.Text(), nullable=True),
    sa.Column('status_code', sa.Integer(), nullable=True),
    sa.Column('request_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('response_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.CheckConstraint("action IN ('api_request', 'db_change', 'external_call')", name='logs_action_check'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_logs_created_at', 'logs', ['created_at'], unique=False)
    op.create_index('idx_logs_request_id', 'logs', ['request_id'], unique=False)
    op.create_index('idx_logs_target_record_id', 'logs', ['target', 'record_id'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_logs_target_record_id', table_name='logs')
    op.drop_index('idx_logs_request_id', table_name='logs')
    op.drop_index('idx_logs_created_at', table_name='logs')
    op.drop_table('logs')
