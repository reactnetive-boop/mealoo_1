"""add audit_logs table

Revision ID: e5f6a1b2c3d4
Revises: d4e5f6a1b2c3
Create Date: 2026-06-16 17:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e5f6a1b2c3d4'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a1b2c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Partitioned table — must use raw SQL because PARTITION BY is not
    # supported by op.create_table
    op.execute("""
        CREATE TABLE IF NOT EXISTS master.audit_logs (
            id          BIGSERIAL,
            table_name  CHARACTER VARYING(100)  NOT NULL,
            record_id   UUID,
            operation   CHARACTER(1)            NOT NULL,
            old_data    JSONB,
            new_data    JSONB,
            changed_by  UUID,
            changed_by_type CHARACTER VARYING(100),
            ip_address  INET,
            created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            CONSTRAINT audit_logs_pkey PRIMARY KEY (id, created_at),
            CONSTRAINT audit_logs_operation_check
                CHECK (operation IN ('I', 'U', 'D'))
        ) PARTITION BY RANGE (created_at)
    """)

    op.create_index(
        'idx_audit_changed_by',
        'audit_logs',
        ['changed_by'],
        unique=False,
        schema='master'
    )
    op.create_index(
        'idx_audit_table_record',
        'audit_logs',
        ['table_name', 'record_id'],
        unique=False,
        schema='master'
    )


def downgrade() -> None:
    op.drop_index('idx_audit_table_record', table_name='audit_logs', schema='master')
    op.drop_index('idx_audit_changed_by', table_name='audit_logs', schema='master')
    op.execute("DROP TABLE IF EXISTS master.audit_logs")
