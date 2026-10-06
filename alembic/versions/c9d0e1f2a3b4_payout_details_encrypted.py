"""kitchen payout details; bank account numbers encrypted at rest

Kitchens can request withdrawals, so they need somewhere to say where the
money goes (provider.provider_payout_details, same shape as the partners').
Account numbers of both are now stored encrypted (app.core.crypto): the
column becomes text and existing plain-text numbers are encrypted here.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-10-05 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "provider_payout_details",
        sa.Column("provider_payout_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "provider_reference_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("provider.providers.provider_id", name="provider_payout_provider_id_fkey"),
            nullable=False, unique=True,
        ),
        sa.Column("account_holder_name", sa.String(128)),
        sa.Column("account_number", sa.Text()),
        sa.Column("ifsc_code", sa.String(20)),
        sa.Column("bank_name", sa.String(128)),
        sa.Column("upi_id", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        schema="provider",
    )
    op.alter_column(
        "delivery_boy_payout_details", "account_number", type_=sa.Text(), existing_type=sa.String(30),
        schema="delivery",
    )
    from app.core.crypto import encrypt, is_encrypted

    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT delivery_boy_payout_id, account_number FROM delivery.delivery_boy_payout_details "
        "WHERE account_number IS NOT NULL"
    )).all()
    for row_id, number in rows:
        if not is_encrypted(number):
            conn.execute(
                sa.text("UPDATE delivery.delivery_boy_payout_details SET account_number = :v "
                        "WHERE delivery_boy_payout_id = :i"),
                {"v": encrypt(number), "i": row_id},
            )


def downgrade() -> None:
    from app.core.crypto import decrypt

    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT delivery_boy_payout_id, account_number FROM delivery.delivery_boy_payout_details "
        "WHERE account_number IS NOT NULL"
    )).all()
    for row_id, number in rows:
        conn.execute(
            sa.text("UPDATE delivery.delivery_boy_payout_details SET account_number = :v "
                    "WHERE delivery_boy_payout_id = :i"),
            {"v": decrypt(number), "i": row_id},
        )
    op.alter_column(
        "delivery_boy_payout_details", "account_number", type_=sa.String(30), existing_type=sa.Text(),
        schema="delivery",
    )
    op.drop_table("provider_payout_details", schema="provider")
