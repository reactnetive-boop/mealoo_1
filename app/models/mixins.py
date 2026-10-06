from sqlalchemy import Column, DateTime, Integer, SmallInteger


class AccountSecurityMixin:
    """
    Columns every login-capable account carries.

    token_version: embedded in each JWT as "ver"; bumping it (logout,
    password change, deactivation) invalidates every token issued before.
    failed_login_count / locked_until: per-account brute-force lockout that
    holds across API replicas.
    """

    token_version = Column(Integer, nullable=False, default=0, server_default="0")

    failed_login_count = Column(SmallInteger, nullable=False, default=0, server_default="0")

    locked_until = Column(DateTime(timezone=True), nullable=True)
