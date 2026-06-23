"""rename id columns to named PKs and FK columns to _reference_id

Revision ID: a0b1c2d3e4f5
Revises: 0c9b8a7f2e1d
Create Date: 2026-06-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'a0b1c2d3e4f5'
down_revision: Union[str, None] = '0c9b8a7f2e1d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── master schema ─────────────────────────────────────────────────────────

    # admin_users: id → admin_user_id
    op.alter_column('admin_users', 'id', new_column_name='admin_user_id', schema='master')

    # audit_logs: id → audit_log_id
    op.alter_column('audit_logs', 'id', new_column_name='audit_log_id', schema='master')

    # subscription_plans: id → subscription_plan_id
    op.alter_column('subscription_plans', 'id', new_column_name='subscription_plan_id', schema='master')

    # menu_packages: category_id → category_reference_id (FK)
    op.alter_column('menu_packages', 'category_id', new_column_name='category_reference_id', schema='master')

    # menu_package_images: package_id → package_reference_id (FK)
    op.alter_column('menu_package_images', 'package_id', new_column_name='package_reference_id', schema='master')

    # menu_package_items: package_id → package_reference_id (FK)
    op.alter_column('menu_package_items', 'package_id', new_column_name='package_reference_id', schema='master')

    # ── auth schema ───────────────────────────────────────────────────────────

    # otp_logs: id → otp_log_id
    op.alter_column('otp_logs', 'id', new_column_name='otp_log_id', schema='auth')

    # user_addresses: id → user_address_id; user_id → user_reference_id (FK)
    op.alter_column('user_addresses', 'id', new_column_name='user_address_id', schema='auth')
    op.alter_column('user_addresses', 'user_id', new_column_name='user_reference_id', schema='auth')

    # user_sessions: id → user_session_id; user_id → user_reference_id (FK)
    op.alter_column('user_sessions', 'id', new_column_name='user_session_id', schema='auth')
    op.alter_column('user_sessions', 'user_id', new_column_name='user_reference_id', schema='auth')

    # notifications: id → notification_id; user_id → user_reference_id (FK)
    op.alter_column('notifications', 'id', new_column_name='notification_id', schema='auth')
    op.alter_column('notifications', 'user_id', new_column_name='user_reference_id', schema='auth')

    # ── delivery schema ───────────────────────────────────────────────────────

    # delivery_boy_otp_logs: id → delivery_boy_otp_log_id
    op.alter_column('delivery_boy_otp_logs', 'id', new_column_name='delivery_boy_otp_log_id', schema='delivery')

    # delivery_boys: assigned_provider_id → assigned_provider_reference_id (FK)
    op.alter_column('delivery_boys', 'assigned_provider_id', new_column_name='assigned_provider_reference_id', schema='delivery')

    # ── subscription schema ───────────────────────────────────────────────────

    # wallets: id → wallet_id; user_id → user_reference_id (FK)
    op.alter_column('wallets', 'id', new_column_name='wallet_id', schema='subscription')
    op.alter_column('wallets', 'user_id', new_column_name='user_reference_id', schema='subscription')

    # wallet_transactions: id → wallet_transaction_id; wallet_id → wallet_reference_id; user_id → user_reference_id
    op.alter_column('wallet_transactions', 'id', new_column_name='wallet_transaction_id', schema='subscription')
    op.alter_column('wallet_transactions', 'wallet_id', new_column_name='wallet_reference_id', schema='subscription')
    op.alter_column('wallet_transactions', 'user_id', new_column_name='user_reference_id', schema='subscription')

    # subscriptions: id → subscription_id; all FK columns
    op.alter_column('subscriptions', 'id', new_column_name='subscription_id', schema='subscription')
    op.alter_column('subscriptions', 'user_id', new_column_name='user_reference_id', schema='subscription')
    op.alter_column('subscriptions', 'vendor_id', new_column_name='vendor_reference_id', schema='subscription')
    op.alter_column('subscriptions', 'plan_id', new_column_name='plan_reference_id', schema='subscription')
    op.alter_column('subscriptions', 'user_address_id', new_column_name='user_address_reference_id', schema='subscription')

    # subscription_packages: id → subscription_package_id; FK columns
    op.alter_column('subscription_packages', 'id', new_column_name='subscription_package_id', schema='subscription')
    op.alter_column('subscription_packages', 'subscription_id', new_column_name='subscription_reference_id', schema='subscription')
    op.alter_column('subscription_packages', 'package_id', new_column_name='package_reference_id', schema='subscription')

    # orders: id → order_id; all FK columns
    op.alter_column('orders', 'id', new_column_name='order_id', schema='subscription')
    op.alter_column('orders', 'subscription_id', new_column_name='subscription_reference_id', schema='subscription')
    op.alter_column('orders', 'user_id', new_column_name='user_reference_id', schema='subscription')
    op.alter_column('orders', 'vendor_id', new_column_name='vendor_reference_id', schema='subscription')
    op.alter_column('orders', 'delivery_address_id', new_column_name='delivery_address_reference_id', schema='subscription')
    op.alter_column('orders', 'delivery_boy_id', new_column_name='delivery_boy_reference_id', schema='subscription')

    # extra_orders: id → extra_order_id; all FK columns
    op.alter_column('extra_orders', 'id', new_column_name='extra_order_id', schema='subscription')
    op.alter_column('extra_orders', 'user_id', new_column_name='user_reference_id', schema='subscription')
    op.alter_column('extra_orders', 'vendor_id', new_column_name='vendor_reference_id', schema='subscription')
    op.alter_column('extra_orders', 'address_id', new_column_name='address_reference_id', schema='subscription')
    op.alter_column('extra_orders', 'package_id', new_column_name='package_reference_id', schema='subscription')
    op.alter_column('extra_orders', 'delivery_boy_id', new_column_name='delivery_boy_reference_id', schema='subscription')

    # payments: id → payment_id; all FK columns
    op.alter_column('payments', 'id', new_column_name='payment_id', schema='subscription')
    op.alter_column('payments', 'subscription_id', new_column_name='subscription_reference_id', schema='subscription')
    op.alter_column('payments', 'user_id', new_column_name='user_reference_id', schema='subscription')
    op.alter_column('payments', 'extra_order_id', new_column_name='extra_order_reference_id', schema='subscription')

    # ── provider schema ───────────────────────────────────────────────────────

    # reviews: id → review_id; all FK columns
    op.alter_column('reviews', 'id', new_column_name='review_id', schema='provider')
    op.alter_column('reviews', 'user_id', new_column_name='user_reference_id', schema='provider')
    op.alter_column('reviews', 'subscription_id', new_column_name='subscription_reference_id', schema='provider')
    op.alter_column('reviews', 'vendor_id', new_column_name='vendor_reference_id', schema='provider')
    op.alter_column('reviews', 'order_id', new_column_name='order_reference_id', schema='provider')
    op.alter_column('reviews', 'package_id', new_column_name='package_reference_id', schema='provider')

    # complaints: id → complaint_id; all FK columns
    op.alter_column('complaints', 'id', new_column_name='complaint_id', schema='provider')
    op.alter_column('complaints', 'user_id', new_column_name='user_reference_id', schema='provider')
    op.alter_column('complaints', 'subscription_id', new_column_name='subscription_reference_id', schema='provider')
    op.alter_column('complaints', 'vendor_id', new_column_name='vendor_reference_id', schema='provider')
    op.alter_column('complaints', 'order_id', new_column_name='order_reference_id', schema='provider')

    # provider_complaints: id → provider_complaint_id; FK columns
    op.alter_column('provider_complaints', 'id', new_column_name='provider_complaint_id', schema='provider')
    op.alter_column('provider_complaints', 'provider_id', new_column_name='provider_reference_id', schema='provider')
    op.alter_column('provider_complaints', 'delivery_boy_id', new_column_name='delivery_boy_reference_id', schema='provider')

    # provider_unavailability: id → provider_unavailability_id; provider_id → provider_reference_id (FK)
    op.alter_column('provider_unavailability', 'id', new_column_name='provider_unavailability_id', schema='provider')
    op.alter_column('provider_unavailability', 'provider_id', new_column_name='provider_reference_id', schema='provider')

    # provider_wallets: id → provider_wallet_id; provider_id → provider_reference_id (FK)
    op.alter_column('provider_wallets', 'id', new_column_name='provider_wallet_id', schema='provider')
    op.alter_column('provider_wallets', 'provider_id', new_column_name='provider_reference_id', schema='provider')

    # provider_wallet_transactions: id → provider_wallet_transaction_id; FK columns
    op.alter_column('provider_wallet_transactions', 'id', new_column_name='provider_wallet_transaction_id', schema='provider')
    op.alter_column('provider_wallet_transactions', 'wallet_id', new_column_name='wallet_reference_id', schema='provider')
    op.alter_column('provider_wallet_transactions', 'provider_id', new_column_name='provider_reference_id', schema='provider')


def downgrade() -> None:
    # ── provider schema ───────────────────────────────────────────────────────

    op.alter_column('provider_wallet_transactions', 'provider_wallet_transaction_id', new_column_name='id', schema='provider')
    op.alter_column('provider_wallet_transactions', 'wallet_reference_id', new_column_name='wallet_id', schema='provider')
    op.alter_column('provider_wallet_transactions', 'provider_reference_id', new_column_name='provider_id', schema='provider')

    op.alter_column('provider_wallets', 'provider_wallet_id', new_column_name='id', schema='provider')
    op.alter_column('provider_wallets', 'provider_reference_id', new_column_name='provider_id', schema='provider')

    op.alter_column('provider_unavailability', 'provider_unavailability_id', new_column_name='id', schema='provider')
    op.alter_column('provider_unavailability', 'provider_reference_id', new_column_name='provider_id', schema='provider')

    op.alter_column('provider_complaints', 'provider_complaint_id', new_column_name='id', schema='provider')
    op.alter_column('provider_complaints', 'provider_reference_id', new_column_name='provider_id', schema='provider')
    op.alter_column('provider_complaints', 'delivery_boy_reference_id', new_column_name='delivery_boy_id', schema='provider')

    op.alter_column('complaints', 'complaint_id', new_column_name='id', schema='provider')
    op.alter_column('complaints', 'user_reference_id', new_column_name='user_id', schema='provider')
    op.alter_column('complaints', 'subscription_reference_id', new_column_name='subscription_id', schema='provider')
    op.alter_column('complaints', 'vendor_reference_id', new_column_name='vendor_id', schema='provider')
    op.alter_column('complaints', 'order_reference_id', new_column_name='order_id', schema='provider')

    op.alter_column('reviews', 'review_id', new_column_name='id', schema='provider')
    op.alter_column('reviews', 'user_reference_id', new_column_name='user_id', schema='provider')
    op.alter_column('reviews', 'subscription_reference_id', new_column_name='subscription_id', schema='provider')
    op.alter_column('reviews', 'vendor_reference_id', new_column_name='vendor_id', schema='provider')
    op.alter_column('reviews', 'order_reference_id', new_column_name='order_id', schema='provider')
    op.alter_column('reviews', 'package_reference_id', new_column_name='package_id', schema='provider')

    # ── subscription schema ───────────────────────────────────────────────────

    op.alter_column('payments', 'payment_id', new_column_name='id', schema='subscription')
    op.alter_column('payments', 'subscription_reference_id', new_column_name='subscription_id', schema='subscription')
    op.alter_column('payments', 'user_reference_id', new_column_name='user_id', schema='subscription')
    op.alter_column('payments', 'extra_order_reference_id', new_column_name='extra_order_id', schema='subscription')

    op.alter_column('extra_orders', 'extra_order_id', new_column_name='id', schema='subscription')
    op.alter_column('extra_orders', 'user_reference_id', new_column_name='user_id', schema='subscription')
    op.alter_column('extra_orders', 'vendor_reference_id', new_column_name='vendor_id', schema='subscription')
    op.alter_column('extra_orders', 'address_reference_id', new_column_name='address_id', schema='subscription')
    op.alter_column('extra_orders', 'package_reference_id', new_column_name='package_id', schema='subscription')
    op.alter_column('extra_orders', 'delivery_boy_reference_id', new_column_name='delivery_boy_id', schema='subscription')

    op.alter_column('orders', 'order_id', new_column_name='id', schema='subscription')
    op.alter_column('orders', 'subscription_reference_id', new_column_name='subscription_id', schema='subscription')
    op.alter_column('orders', 'user_reference_id', new_column_name='user_id', schema='subscription')
    op.alter_column('orders', 'vendor_reference_id', new_column_name='vendor_id', schema='subscription')
    op.alter_column('orders', 'delivery_address_reference_id', new_column_name='delivery_address_id', schema='subscription')
    op.alter_column('orders', 'delivery_boy_reference_id', new_column_name='delivery_boy_id', schema='subscription')

    op.alter_column('subscription_packages', 'subscription_package_id', new_column_name='id', schema='subscription')
    op.alter_column('subscription_packages', 'subscription_reference_id', new_column_name='subscription_id', schema='subscription')
    op.alter_column('subscription_packages', 'package_reference_id', new_column_name='package_id', schema='subscription')

    op.alter_column('subscriptions', 'subscription_id', new_column_name='id', schema='subscription')
    op.alter_column('subscriptions', 'user_reference_id', new_column_name='user_id', schema='subscription')
    op.alter_column('subscriptions', 'vendor_reference_id', new_column_name='vendor_id', schema='subscription')
    op.alter_column('subscriptions', 'plan_reference_id', new_column_name='plan_id', schema='subscription')
    op.alter_column('subscriptions', 'user_address_reference_id', new_column_name='user_address_id', schema='subscription')

    op.alter_column('wallet_transactions', 'wallet_transaction_id', new_column_name='id', schema='subscription')
    op.alter_column('wallet_transactions', 'wallet_reference_id', new_column_name='wallet_id', schema='subscription')
    op.alter_column('wallet_transactions', 'user_reference_id', new_column_name='user_id', schema='subscription')

    op.alter_column('wallets', 'wallet_id', new_column_name='id', schema='subscription')
    op.alter_column('wallets', 'user_reference_id', new_column_name='user_id', schema='subscription')

    # ── delivery schema ───────────────────────────────────────────────────────

    op.alter_column('delivery_boy_otp_logs', 'delivery_boy_otp_log_id', new_column_name='id', schema='delivery')
    op.alter_column('delivery_boys', 'assigned_provider_reference_id', new_column_name='assigned_provider_id', schema='delivery')

    # ── auth schema ───────────────────────────────────────────────────────────

    op.alter_column('notifications', 'notification_id', new_column_name='id', schema='auth')
    op.alter_column('notifications', 'user_reference_id', new_column_name='user_id', schema='auth')

    op.alter_column('user_sessions', 'user_session_id', new_column_name='id', schema='auth')
    op.alter_column('user_sessions', 'user_reference_id', new_column_name='user_id', schema='auth')

    op.alter_column('user_addresses', 'user_address_id', new_column_name='id', schema='auth')
    op.alter_column('user_addresses', 'user_reference_id', new_column_name='user_id', schema='auth')

    op.alter_column('otp_logs', 'otp_log_id', new_column_name='id', schema='auth')

    # ── master schema ─────────────────────────────────────────────────────────

    op.alter_column('menu_package_items', 'package_reference_id', new_column_name='package_id', schema='master')
    op.alter_column('menu_package_images', 'package_reference_id', new_column_name='package_id', schema='master')
    op.alter_column('menu_packages', 'category_reference_id', new_column_name='category_id', schema='master')

    op.alter_column('subscription_plans', 'subscription_plan_id', new_column_name='id', schema='master')
    op.alter_column('audit_logs', 'audit_log_id', new_column_name='id', schema='master')
    op.alter_column('admin_users', 'admin_user_id', new_column_name='id', schema='master')
