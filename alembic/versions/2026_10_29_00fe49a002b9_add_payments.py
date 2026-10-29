"""add payments

Payments of carts (versioned: payments_history keeps every change) and the
credit/debit type of each payment method. Existing payment methods become
credit cards.

Revision ID: 00fe49a002b9
Revises: 35867345c126
Create Date: 2026-10-29 16:10:08.069185

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '00fe49a002b9'
down_revision: Union[str, None] = '35867345c126'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('payments_history',
    sa.Column('history_id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('cart_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('payment_method_id', sa.Uuid(), nullable=False),
    sa.Column('payment_type', sa.Text(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('currency', sa.CHAR(length=3), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('provider_transaction_id', sa.Text(), nullable=True),
    sa.Column('failure_reason', sa.Text(), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('operation', sa.Text(), nullable=False),
    sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.CheckConstraint("operation IN ('insert', 'update', 'delete')", name='payments_history_operation_check'),
    sa.PrimaryKeyConstraint('history_id'),
    sa.UniqueConstraint('id', 'version', name='uq_payments_history_id_version')
    )
    op.create_table('payments',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('cart_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('payment_method_id', sa.Uuid(), nullable=False),
    sa.Column('payment_type', sa.Text(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('currency', sa.CHAR(length=3), nullable=False),
    sa.Column('status', sa.Text(), server_default='pending', nullable=False),
    sa.Column('provider_transaction_id', sa.Text(), nullable=True),
    sa.Column('failure_reason', sa.Text(), nullable=True),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("payment_type IN ('credit', 'debit')", name='payments_payment_type_check'),
    sa.CheckConstraint("status IN ('pending', 'succeeded', 'failed')", name='payments_status_check'),
    sa.CheckConstraint('amount > 0', name='payments_amount_check'),
    sa.ForeignKeyConstraint(['cart_id'], ['carts.id'], ),
    sa.ForeignKeyConstraint(['payment_method_id'], ['user_payment_methods.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_payments_cart_id', 'payments', ['cart_id'], unique=False)
    op.create_index('idx_payments_user_id', 'payments', ['user_id'], unique=False)
    op.create_index('uq_payments_cart_id_active', 'payments', ['cart_id'], unique=True, postgresql_where=sa.text("status IN ('pending', 'succeeded') AND deleted_at IS NULL"))
    # Existing payment methods get "credit"; new ones must always say their type.
    op.add_column('user_payment_methods', sa.Column('type', sa.Text(), server_default='credit', nullable=False))
    op.alter_column('user_payment_methods', 'type', server_default=None)
    op.create_check_constraint('user_payment_methods_type_check', 'user_payment_methods', "type IN ('credit', 'debit')")


def downgrade() -> None:
    op.drop_constraint('user_payment_methods_type_check', 'user_payment_methods', type_='check')
    op.drop_column('user_payment_methods', 'type')
    op.drop_index('uq_payments_cart_id_active', table_name='payments', postgresql_where=sa.text("status IN ('pending', 'succeeded') AND deleted_at IS NULL"))
    op.drop_index('idx_payments_user_id', table_name='payments')
    op.drop_index('idx_payments_cart_id', table_name='payments')
    op.drop_table('payments')
    op.drop_table('payments_history')
