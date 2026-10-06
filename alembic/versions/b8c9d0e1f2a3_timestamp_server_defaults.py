"""timestamps are set by the database everywhere

created_at / updated_at of users, addresses, kitchens, offerings and OTP
rows were filled in by Python. They now default to now() in the database
(rows written by SQL, imports or other services get them too), and the two
remaining columns without a time zone become timestamptz.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-05 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULTS = (
    ("auth", "users", "created_at"),
    ("auth", "users", "updated_at"),
    ("auth", "user_addresses", "created_at"),
    ("auth", "user_addresses", "updated_at"),
    ("auth", "otp_logs", "created_at"),
    ("provider", "providers", "created_at"),
    ("provider", "providers", "updated_at"),
    ("provider", "otp_logs", "created_at"),
    ("provider", "provider_selected_packages", "created_at"),
)

# naive columns written with the session's time zone
TO_TIMESTAMPTZ = (
    ("provider", "provider_selected_packages", "created_at"),
    ("master", "serviceable_pincodes", "created_at"),
)


def upgrade() -> None:
    for schema, table, column in TO_TIMESTAMPTZ:
        op.execute(
            f"ALTER TABLE {schema}.{table} ALTER COLUMN {column} TYPE timestamptz "
            f"USING {column} AT TIME ZONE current_setting('TimeZone')"
        )
    for schema, table, column in DEFAULTS:
        op.execute(f"ALTER TABLE {schema}.{table} ALTER COLUMN {column} SET DEFAULT now()")
        op.execute(f"UPDATE {schema}.{table} SET {column} = now() WHERE {column} IS NULL")


def downgrade() -> None:
    for schema, table, column in DEFAULTS:
        op.execute(f"ALTER TABLE {schema}.{table} ALTER COLUMN {column} DROP DEFAULT")
    for schema, table, column in TO_TIMESTAMPTZ:
        op.execute(
            f"ALTER TABLE {schema}.{table} ALTER COLUMN {column} TYPE timestamp "
            f"USING {column} AT TIME ZONE current_setting('TimeZone')"
        )
