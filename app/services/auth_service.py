"""Kitchen (provider) app accounts."""

from app.core.security import ROLE_PROVIDER
from app.models.otp_log_model import OTPLog
from app.repositories.provider_repository import ProviderRepository
from app.services.account_auth import AccountAuth
from app.services.auth_common import OtpTable


class ProviderAccountAuth(AccountAuth):
    role = ROLE_PROVIDER
    otp = OtpTable(model=OTPLog, identity="mobile_number", code="otp", used="is_verified")
    password_field = "hashed_password"
    id_field = "provider_id"
    contact_field = "mobile_number"
    # A new kitchen must complete its profile and wait for approval before anything else
    signs_in_on_register = False
    reset_otp_password = ""

    def find_by_phone(self, db, phone):
        return ProviderRepository.get_by_mobile(db, phone)

    def find_by_id(self, db, account_id):
        return ProviderRepository.get_by_provider_id(db, account_id)

    def create(self, db, phone, password_hash, **fields):
        return ProviderRepository.create_provider(db, {
            "mobile_number": phone,
            "hashed_password": password_hash,
            "is_mobile_verified": True,
            "is_profile_completed": False,
            "approval_status": "pending",
        })

    def is_active(self, account):
        return bool(account.is_active)

    def inactive_message(self, account):
        return "Your kitchen account is inactive. Please contact support."

    def token_claims(self, account):
        return {"provider_id": str(account.provider_id), "mobile_number": account.mobile_number}

    def account_fields(self, account):
        return {
            "is_profile_completed": bool(account.is_profile_completed),
            "approval_status": account.approval_status,
        }


AuthService = ProviderAccountAuth()
