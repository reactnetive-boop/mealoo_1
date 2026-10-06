"""Delivery partner app accounts."""

from app.core.security import ROLE_DELIVERY
from app.models.delivery_boy_otp_log_model import DeliveryBoyOTPLog
from app.repositories.delivery_boy_repository import DeliveryBoyRepository
from app.services.account_auth import AccountAuth
from app.services.auth_common import OtpTable


def _profile_completed(boy) -> bool:
    return bool(boy.full_name and boy.vehicle_type)


class DeliveryPartnerAccountAuth(AccountAuth):
    role = ROLE_DELIVERY
    otp = OtpTable(model=DeliveryBoyOTPLog, identity="mobile_number", code="otp", used="is_verified")
    password_field = "hashed_password"
    id_field = "delivery_boy_id"
    reset_otp_password = ""

    def find_by_phone(self, db, phone):
        return DeliveryBoyRepository.get_by_mobile(db, phone)

    def find_by_id(self, db, account_id):
        return DeliveryBoyRepository.get_by_id(db, account_id)

    def create(self, db, phone, password_hash, **fields):
        # New partners start offline and pending admin approval
        return DeliveryBoyRepository.create(db, {
            "mobile_number": phone,
            "hashed_password": password_hash,
            "is_mobile_verified": True,
            "is_active": True,
            "is_online": False,
            "approval_status": "pending",
        })

    def is_active(self, account):
        return bool(account.is_active)

    def inactive_message(self, account):
        return "Account is deactivated. Please contact support."

    def token_claims(self, account):
        return {"delivery_boy_id": str(account.delivery_boy_id), "mobile_number": account.mobile_number}

    def account_fields(self, account):
        return {"is_profile_completed": _profile_completed(account)}

    def on_logout(self, account):
        account.is_online = False


DeliveryBoyAuthService = DeliveryPartnerAccountAuth()
