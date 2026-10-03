"""
Withdrawals for kitchens and delivery partners.

Requesting a withdrawal moves the amount out of the available balance into a
pending request (a 'withdrawal_hold' debit), so it cannot be spent or
requested twice. An admin then either marks it paid after the offline bank /
UPI transfer (no real payout integration in this phase) - the amount then
counts as withdrawn - or rejects it, which returns the hold to the wallet.
"""

from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit import business_event, record_audit
from app.core.clock import now_utc
from app.core.errors import DomainError
from app.domain import ledger, notify
from app.domain.pricing import money
from app.models.delivery_boy_payout_model import DeliveryBoyPayoutDetails
from app.models.payout_request_model import PayoutRequest
from app.models.provider_wallet_model import ProviderWallet
from app.models.delivery_boy_wallet_model import DeliveryBoyWallet

MIN_WITHDRAWAL = Decimal("1.00")


def _post(db: Session, owner_type: str, owner_id, **kwargs):
    if owner_type == "provider":
        return ledger.post_provider(db, owner_id, **kwargs)
    return ledger.post_delivery(db, owner_id, **kwargs)


def _view(r: PayoutRequest) -> dict:
    return {
        "payout_request_id": r.payout_request_id,
        "owner_type": r.owner_type,
        "owner_id": r.owner_id,
        "amount": r.amount,
        "status": r.status,
        "note": r.note,
        "admin_note": r.admin_note,
        "payout_reference": r.payout_reference,
        "requested_at": r.requested_at,
        "processed_at": r.processed_at,
    }


class PayoutService:

    @staticmethod
    def request(db: Session, owner_type: str, owner_id: str, amount, note: str | None):
        amount = money(amount)
        if amount < MIN_WITHDRAWAL:
            raise DomainError(f"Minimum withdrawal is Rs {MIN_WITHDRAWAL}")

        if owner_type == "delivery_boy":
            payout = db.query(DeliveryBoyPayoutDetails).filter(
                DeliveryBoyPayoutDetails.delivery_boy_reference_id == owner_id
            ).first()
            if payout is None or not (payout.upi_id or (payout.account_number and payout.ifsc_code)):
                raise DomainError("Add your bank account or UPI ID before requesting a withdrawal")

        pending = db.query(PayoutRequest).filter(
            PayoutRequest.owner_type == owner_type,
            PayoutRequest.owner_id == owner_id,
            PayoutRequest.status == "pending",
        ).count()
        if pending >= 3:
            raise DomainError("You already have 3 withdrawal requests waiting for approval")

        request = PayoutRequest(owner_type=owner_type, owner_id=owner_id, amount=amount, status="pending", note=note)
        db.add(request)
        db.flush()
        # Raises InsufficientBalance (and rolls everything back) if the balance is short
        _post(
            db, owner_type, owner_id,
            type="debit", amount=amount, reason="withdrawal_hold",
            idempotency_key=f"payout_hold:{request.payout_request_id}",
            reference_type="payout_request", reference_id=request.payout_request_id,
            description=note or "Withdrawal requested - waiting for approval",
        )
        db.commit()
        business_event("payout.requested", owner_type=owner_type, owner_id=owner_id, amount=amount)
        return {
            "success": True,
            "message": "Withdrawal requested. The amount is on hold until Orleeno processes it.",
            "request": _view(request),
        }

    @staticmethod
    def list_for_owner(db: Session, owner_type: str, owner_id: str):
        rows = (
            db.query(PayoutRequest)
            .filter(PayoutRequest.owner_type == owner_type, PayoutRequest.owner_id == owner_id)
            .order_by(PayoutRequest.requested_at.desc())
            .limit(100)
            .all()
        )
        return {"success": True, "total": len(rows), "requests": [_view(r) for r in rows]}

    @staticmethod
    def list_all(db: Session, status: str | None, owner_type: str | None, page: int, limit: int):
        q = db.query(PayoutRequest)
        if status:
            q = q.filter(PayoutRequest.status == status)
        if owner_type:
            q = q.filter(PayoutRequest.owner_type == owner_type)
        total = q.count()
        rows = q.order_by(PayoutRequest.requested_at.desc()).offset((page - 1) * limit).limit(limit).all()
        return {"success": True, "total": total, "requests": [_view(r) for r in rows]}

    @staticmethod
    def process(db: Session, request_id, *, approve: bool, admin_id: str, admin_note: str | None, payout_reference: str | None, ip: str | None = None):
        request = db.query(PayoutRequest).filter(PayoutRequest.payout_request_id == request_id).with_for_update().first()
        if request is None:
            raise HTTPException(status_code=404, detail="Withdrawal request not found")
        if request.status != "pending":
            raise DomainError(f"This request is already {request.status}", 409)

        before = _view(request)
        if approve:
            if not payout_reference:
                raise DomainError("Enter the bank / UPI transaction reference of the payout")
            request.status = "paid"
            request.payout_reference = payout_reference
            wallet_model = ProviderWallet if request.owner_type == "provider" else DeliveryBoyWallet
            owner_col = (
                ProviderWallet.provider_reference_id if request.owner_type == "provider"
                else DeliveryBoyWallet.delivery_boy_reference_id
            )
            wallet = db.query(wallet_model).filter(owner_col == request.owner_id).with_for_update().one()
            wallet.total_withdrawn = money(wallet.total_withdrawn) + money(request.amount)
        else:
            request.status = "rejected"
            _post(
                db, request.owner_type, request.owner_id,
                type="credit", amount=request.amount, reason="withdrawal_reversal",
                idempotency_key=f"payout_reversal:{request.payout_request_id}",
                reference_type="payout_request", reference_id=request.payout_request_id,
                description="Withdrawal request rejected - amount returned",
            )

        request.admin_note = admin_note
        request.processed_at = now_utc()
        request.processed_by = admin_id
        record_audit(
            db, table="subscription.payout_requests", record_id=request.payout_request_id,
            old=before, new=_view(request), actor_id=admin_id, actor_type="admin", ip=ip,
        )
        if request.owner_type == "delivery_boy":
            notify.delivery_partner(
                db, request.owner_id, "payout",
                "Withdrawal paid" if approve else "Withdrawal rejected",
                f"Your withdrawal of Rs {request.amount} was {'paid' if approve else 'rejected'}."
                + (f" {admin_note}" if admin_note else ""),
                {"payout_request_id": str(request.payout_request_id)},
            )
        db.commit()
        business_event("payout.processed", request_id=request.payout_request_id, approve=approve, admin_id=admin_id)
        return {"success": True, "message": f"Withdrawal {'marked paid' if approve else 'rejected'}", "request": _view(request)}
