"""otp_logs expires_at and created_at timezone fix

Revision ID: f8a3b4c5d6e7
Revises: e7f8a3b4c5d6
Create Date: 2026-06-16 21:35:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f8a3b4c5d6e7'
down_revision: Union[str, Sequence[str], None] = 'e7f8a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'otp_logs', 'expires_at',
        type_=sa.DateTime(timezone=True),
        existing_type=sa.DateTime(),
        existing_nullable=False,
        schema='provider',
        postgresql_using='expires_at AT TIME ZONE \'UTC\''
    )
    op.alter_column(
        'otp_logs', 'created_at',
        type_=sa.DateTime(timezone=True),
        existing_type=sa.DateTime(),
        existing_nullable=True,
        schema='provider',
        postgresql_using='created_at AT TIME ZONE \'UTC\''
    )


def downgrade() -> None:
    op.alter_column(
        'otp_logs', 'created_at',
        type_=sa.DateTime(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=True,
        schema='provider',
        postgresql_using='created_at AT TIME ZONE \'UTC\''
    )
    op.alter_column(
        'otp_logs', 'expires_at',
        type_=sa.DateTime(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        schema='provider',
        postgresql_using='expires_at AT TIME ZONE \'UTC\''
    )
