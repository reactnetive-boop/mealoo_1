from sqlalchemy import (
    Column,
    BigInteger,
    String,
    DateTime,
    CheckConstraint,
    Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET

from sqlalchemy.sql import func

from app.core.database import Base


class AuditLog(Base):

    __tablename__ = "audit_logs"

    __table_args__ = (
        CheckConstraint(
            "operation IN ('I', 'U', 'D')",
            name="audit_logs_operation_check"
        ),
        Index("idx_audit_changed_by", "changed_by"),
        Index("idx_audit_table_record", "table_name", "record_id"),
        {
            "schema": "master",
            "postgresql_partition_by": "RANGE (created_at)"
        }
    )

    audit_log_id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    table_name = Column(
        String(100),
        nullable=False
    )

    record_id = Column(
        UUID(as_uuid=True),
        nullable=True
    )

    # 'I' = Insert, 'U' = Update, 'D' = Delete
    operation = Column(
        String(1),
        nullable=False
    )

    old_data = Column(
        JSONB,
        nullable=True
    )

    new_data = Column(
        JSONB,
        nullable=True
    )

    changed_by = Column(
        UUID(as_uuid=True),
        nullable=True
    )

    changed_by_type = Column(
        String(100),
        nullable=True
    )

    ip_address = Column(
        INET,
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
