"""version carts

Makes carts a versioned table: adds carts.version and carts_history, which
keeps a snapshot of every change (see VersionedBaseModel). Existing carts get
a version 1 "insert" history row, so every cart has a complete history.

Revision ID: 91bcf7cc5bf7
Revises: 91590c361983
Create Date: 2026-10-28 01:35:47.586560

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '91bcf7cc5bf7'
down_revision: Union[str, None] = '91590c361983'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('carts_history',
    sa.Column('history_id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('operation', sa.Text(), nullable=False),
    sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.CheckConstraint("operation IN ('insert', 'update', 'delete')", name='carts_history_operation_check'),
    sa.PrimaryKeyConstraint('history_id'),
    sa.UniqueConstraint('id', 'version', name='uq_carts_history_id_version')
    )
    op.add_column('carts', sa.Column('version', sa.Integer(), server_default='1', nullable=False))

    op.execute(
        "INSERT INTO carts_history (id, user_id, status, version, deleted_at, operation, changed_at) "
        "SELECT id, user_id, status, version, deleted_at, 'insert', created_at FROM carts"
    )


def downgrade() -> None:
    op.drop_column('carts', 'version')
    op.drop_table('carts_history')
