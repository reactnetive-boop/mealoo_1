"""
Where withdrawals are sent: a bank account and / or a UPI ID, for kitchens,
delivery partners and customers (wallet withdrawals) alike. Account numbers
are encrypted at rest; owners see their own details, admins see them masked
in lists and in full only through an audited reveal (needed for the transfer).
"""

from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.errors import DomainError
from app.models.delivery_boy_payout_model import DeliveryBoyPayoutDetails
from app.models.provider_payout_model import ProviderPayoutDetails
from app.models.user_payout_model import UserPayoutDetails
from app.services.admin_views import payout_details_view

_OWNERS = {
    "provider": (ProviderPayoutDetails, "provider_reference_id", "provider.provider_payout_details"),
    "delivery_boy": (DeliveryBoyPayoutDetails, "delivery_boy_reference_id", "delivery.delivery_boy_payout_details"),
    "customer": (UserPayoutDetails, "user_reference_id", "auth.user_payout_details"),
}
FIELDS = ("account_holder_name", "account_number", "ifsc_code", "bank_name", "upi_id")


def _owner(owner_type: str):
    try:
        return _OWNERS[owner_type]
    except KeyError:
        raise ValueError(f"unknown payout owner type {owner_type!r}") from None


def find(db: Session, owner_type: str, owner_id):
    model, column, _ = _owner(owner_type)
    return db.query(model).filter(getattr(model, column) == owner_id).first()


def find_many(db: Session, owner_type: str, owner_ids) -> dict:
    model, column, _ = _owner(owner_type)
    if not owner_ids:
        return {}
    rows = db.query(model).filter(getattr(model, column).in_(list(owner_ids))).all()
    return {getattr(r, column): r for r in rows}


def is_ready(details) -> bool:
    return bool(details and (details.upi_id or (details.account_number and details.ifsc_code)))


class PayoutDetailsService:

    @staticmethod
    def get_own(db: Session, owner_type: str, owner_id) -> dict:
        details = find(db, owner_type, owner_id)
        return {"success": True, "ready": is_ready(details), "payout_details": payout_details_view(details, reveal=True)}

    @staticmethod
    def save(db: Session, owner_type: str, owner_id, payload) -> dict:
        data = {k: v for k, v in payload.model_dump().items() if k in FIELDS and v is not None}
        if not data:
            raise DomainError("Nothing to update")
        if "ifsc_code" in data:
            data["ifsc_code"] = data["ifsc_code"].upper()

        model, column, _ = _owner(owner_type)
        details = find(db, owner_type, owner_id)
        if details is None:
            details = model(**{column: owner_id})
            db.add(details)
        for key, value in data.items():
            setattr(details, key, value)

        if (details.account_number or details.ifsc_code) and not (
            details.account_number and details.ifsc_code and details.account_holder_name
        ):
            raise DomainError("For a bank transfer enter the account holder name, account number and IFSC code")
        if not is_ready(details):
            raise DomainError("Add a UPI ID or bank account details")

        db.commit()
        db.refresh(details)
        return {
            "success": True,
            "message": "Payout details saved",
            "ready": True,
            "payout_details": payout_details_view(details, reveal=True),
        }

    @staticmethod
    def reveal_for_admin(db: Session, owner_type: str, owner_id, admin_id: str, ip: str | None = None) -> dict:
        _, _, table = _owner(owner_type)
        details = find(db, owner_type, owner_id)
        # the full number is needed to make the transfer; every view is audited
        record_audit(
            db, table=table, record_id=owner_id, new={"viewed": "payout_details"},
            actor_id=admin_id, actor_type="admin", ip=ip,
        )
        db.commit()
        return {"success": True, "ready": is_ready(details), "payout_details": payout_details_view(details, reveal=True)}
