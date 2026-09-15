"""add purpose to provider otp_logs

Separates registration OTPs from password-reset OTPs so a code issued for one
flow cannot be replayed to drive the other.

Revision ID: c7d8e9f0a1b2
Revises: a4b5c6d7e8f9
Create Date: 2026-09-15 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, Sequence[str], None] = 'a4b5c6d7e8f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing rows were all issued by the registration flow.
    op.add_column(
        'otp_logs',
        sa.Column(
            'purpose',
            sa.String(length=30),
            nullable=False,
            server_default='registration'
        ),
        schema='provider'
    )


def downgrade() -> None:
    op.drop_column(
        'otp_logs',
        'purpose',
        schema='provider'
    )
