"""add package switch logs table (package switch policy audit trail)

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-07-14 16:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from alembic import op


revision: str = 'f4a5b6c7d8e9'
down_revision: Union[str, None] = 'e3f4a5b6c7d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'package_switch_logs',
        sa.Column('package_switch_log_id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_reference_id', UUID(as_uuid=True), nullable=False),
        sa.Column('old_subscription_reference_id', UUID(as_uuid=True), nullable=False),
        sa.Column('new_subscription_reference_id', UUID(as_uuid=True), nullable=True),
        sa.Column('old_provider_reference_id', UUID(as_uuid=True), nullable=False),
        sa.Column('new_provider_reference_id', UUID(as_uuid=True), nullable=False),
        sa.Column('old_package_reference_id', UUID(as_uuid=True), nullable=False),
        sa.Column('new_package_reference_id', UUID(as_uuid=True), nullable=False),
        sa.Column('switch_request_date', sa.Date, nullable=False),
        sa.Column('effective_date', sa.Date, nullable=False),
        sa.Column('total_days', sa.Integer, nullable=False),
        sa.Column('used_days', sa.Integer, nullable=False),
        sa.Column('remaining_days', sa.Integer, nullable=False),
        sa.Column('old_daily_cost', sa.Numeric(10, 2), nullable=False),
        sa.Column('new_daily_cost', sa.Numeric(10, 2), nullable=False),
        sa.Column('remaining_value', sa.Numeric(10, 2), nullable=False),
        sa.Column('new_remaining_cost', sa.Numeric(10, 2), nullable=False),
        sa.Column('adjustment_amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('payment_amount', sa.Numeric(10, 2), nullable=False, server_default='0'),
        sa.Column('wallet_credit_amount', sa.Numeric(10, 2), nullable=False, server_default='0'),
        sa.Column('payment_status', sa.String(20), nullable=False),
        sa.Column('switch_status', sa.String(20), nullable=False, server_default='completed'),
        sa.Column('created_by', sa.String(50), nullable=False, server_default='user'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ['user_reference_id'], ['auth.users.user_id'],
            name='package_switch_logs_user_id_fkey'
        ),
        sa.ForeignKeyConstraint(
            ['old_subscription_reference_id'], ['subscription.subscriptions.subscription_id'],
            name='package_switch_logs_old_sub_fkey'
        ),
        sa.ForeignKeyConstraint(
            ['new_subscription_reference_id'], ['subscription.subscriptions.subscription_id'],
            name='package_switch_logs_new_sub_fkey'
        ),
        sa.ForeignKeyConstraint(
            ['old_provider_reference_id'], ['provider.providers.provider_id'],
            name='package_switch_logs_old_provider_fkey'
        ),
        sa.ForeignKeyConstraint(
            ['new_provider_reference_id'], ['provider.providers.provider_id'],
            name='package_switch_logs_new_provider_fkey'
        ),
        sa.ForeignKeyConstraint(
            ['old_package_reference_id'], ['master.menu_packages.package_id'],
            name='package_switch_logs_old_package_fkey'
        ),
        sa.ForeignKeyConstraint(
            ['new_package_reference_id'], ['master.menu_packages.package_id'],
            name='package_switch_logs_new_package_fkey'
        ),
        schema='subscription'
    )
    op.create_index(
        'idx_package_switch_logs_user',
        'package_switch_logs', ['user_reference_id'],
        schema='subscription'
    )
    op.create_index(
        'idx_package_switch_logs_old_sub',
        'package_switch_logs', ['old_subscription_reference_id'],
        schema='subscription'
    )


def downgrade() -> None:
    op.drop_table('package_switch_logs', schema='subscription')
