"""admin two-factor login (TOTP)

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-10-06 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c6d7e8f9a0b1'
down_revision: Union[str, None] = 'b5c6d7e8f9a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = (
    sa.Column("totp_secret", sa.Text(), nullable=True),
    sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    sa.Column("totp_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("totp_last_step", sa.BigInteger(), nullable=True),
    sa.Column("totp_recovery_hashes", postgresql.JSONB(), nullable=True),
)


def upgrade() -> None:
    for column in COLUMNS:
        op.add_column("admin_users", column, schema="master")


def downgrade() -> None:
    for column in reversed(COLUMNS):
        op.drop_column("admin_users", column.name, schema="master")
