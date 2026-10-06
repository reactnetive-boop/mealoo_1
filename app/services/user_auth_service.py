"""Customer app accounts."""

from app.core.clock import now_utc
from app.core.security import ROLE_CUSTOMER
from app.models.user_otp_log_model import UserOTPLog
from app.repositories.user_repository import UserRepository
from app.services.account_auth import AccountAuth
from app.services.auth_common import OtpTable


class CustomerAccountAuth(AccountAuth):
    role = ROLE_CUSTOMER
    otp = OtpTable(model=UserOTPLog, identity="contact", code="otp_hash", used="is_used")
    password_field = "password_hash"
    id_field = "user_id"
    otp_extra = {"channel": "sms"}

    def find_by_phone(self, db, phone):
        return UserRepository.get_by_phone(db, phone)

    def find_by_id(self, db, account_id):
        return UserRepository.get_by_user_id(db, account_id)

    def create(self, db, phone, password_hash, email=None, **_):
        return UserRepository.create_user(db, {
            "phone": phone,
            "email": email or None,
            "phone_verified": True,
            "email_verified": False,
            "password_hash": password_hash,
            "is_profile_completed": False,
            "status": "active",
        })

    def is_active(self, account):
        return account.status == "active"

    def inactive_message(self, account):
        return f"Your account is {account.status}. Please contact support."

    def token_claims(self, account):
        return {"user_id": str(account.user_id), "contact": account.phone or account.email}

    def account_fields(self, account):
        return {"is_profile_completed": bool(account.is_profile_completed)}

    def on_login(self, account):
        account.last_login_at = now_utc()


UserAuthService = CustomerAccountAuth()
