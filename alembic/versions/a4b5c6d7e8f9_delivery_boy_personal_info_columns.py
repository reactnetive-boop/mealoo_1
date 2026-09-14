"""delivery boys: add email, date_of_birth, gender personal-info columns

Revision ID: a4b5c6d7e8f9
Revises: f4a5b6c7d8e9
Create Date: 2026-07-15 21:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'a4b5c6d7e8f9'
down_revision: Union[str, None] = 'f4a5b6c7d8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('delivery_boys', sa.Column('email', sa.String(255), nullable=True), schema='delivery')
    op.add_column('delivery_boys', sa.Column('date_of_birth', sa.Date, nullable=True), schema='delivery')
    op.add_column('delivery_boys', sa.Column('gender', sa.String(10), nullable=True), schema='delivery')


def downgrade() -> None:
    op.drop_column('delivery_boys', 'gender', schema='delivery')
    op.drop_column('delivery_boys', 'date_of_birth', schema='delivery')
    op.drop_column('delivery_boys', 'email', schema='delivery')
