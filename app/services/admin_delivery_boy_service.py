from sqlalchemy.orm import Session

from app.core.audit import record_audit, business_event
from app.core.clock import now_utc
from app.core.errors import DomainError
from app.domain import notify
from app.domain.delivery_assignment import release_partner_subscriptions
from app.domain.status import (
    SUB_OPEN_STATUSES, EXTRA_OPEN_STATUSES, SUB_UNPICKED_STATUSES, EXTRA_UNPICKED_STATUSES, IN_HAND_STATUSES,
)
from app.models.delivery_boy_model import DeliveryBoy
from app.models.delivery_boy_wallet_model import DeliveryBoyWallet
from app.models.delivery_boy_document_model import DeliveryBoyDocument
from app.models.delivery_boy_payout_model import DeliveryBoyPayoutDetails
from app.models.order_model import Order
from app.models.extra_order_model import ExtraOrder
from app.models.provider_model import Provider
from app.schemas.delivery_boy_schema import DOCUMENT_TYPES
from app.services.admin_views import delivery_boy_view, payout_details_view
from app.services.auth_common import revoke_sessions
from app.services.delivery_boy_account_service import document_file_response

APPROVAL_STATUSES = ("pending", "approved", "rejected")
ACTIVE_SUB_STATUSES = SUB_OPEN_STATUSES
ACTIVE_EXTRA_STATUSES = EXTRA_OPEN_STATUSES


def _boy(db: Session, delivery_boy_id, lock: bool = False) -> DeliveryBoy:
    q = db.query(DeliveryBoy).filter(DeliveryBoy.delivery_boy_id == delivery_boy_id)
    if lock:
        q = q.with_for_update()
    boy = q.first()
    if not boy:
        raise DomainError("Delivery partner not found", 404)
    return boy


def _doc_view(d: DeliveryBoyDocument) -> dict:
    return {
        "delivery_boy_document_id": d.delivery_boy_document_id,
        "document_type": d.document_type,
        "status": d.status,
        "remarks": d.remarks,
        "verified_at": d.verified_at,
        "created_at": d.created_at,
        "updated_at": d.updated_at,
    }


def _out_for_delivery(db: Session, delivery_boy_id) -> int:
    """Orders the partner is carrying right now (picked up, not yet delivered)."""
    return (
        db.query(Order).filter(
            Order.delivery_boy_reference_id == delivery_boy_id, Order.status.in_(IN_HAND_STATUSES)
        ).count()
        + db.query(ExtraOrder).filter(
            ExtraOrder.delivery_boy_reference_id == delivery_boy_id, ExtraOrder.status.in_(IN_HAND_STATUSES)
        ).count()
    )


def _release_open_assignments(db: Session, delivery_boy_id, *, reason: str, admin_id) -> int:
    """
    Unassign meals that have not been picked up, and end the partner's
    subscription assignments, so new meals stop going to them and an admin
    or kitchen can reassign.
    """
    release_partner_subscriptions(db, delivery_boy_id, reason=reason, actor_id=admin_id, actor_type="admin")
    n = (
        db.query(Order)
        .filter(Order.delivery_boy_reference_id == delivery_boy_id, Order.status.in_(SUB_UNPICKED_STATUSES))
        .update({Order.delivery_boy_reference_id: None}, synchronize_session=False)
    )
    n += (
        db.query(ExtraOrder)
        .filter(
            ExtraOrder.delivery_boy_reference_id == delivery_boy_id,
            ExtraOrder.status.in_(EXTRA_UNPICKED_STATUSES),
        )
        .update({ExtraOrder.delivery_boy_reference_id: None}, synchronize_session=False)
    )
    return n


def _wallet(db: Session, delivery_boy_id) -> dict:
    w = db.query(DeliveryBoyWallet).filter(DeliveryBoyWallet.delivery_boy_reference_id == delivery_boy_id).first()
    zero = "0.00"
    return {
        "balance": str(w.balance) if w else zero,
        "total_earned": str(w.total_earned) if w else zero,
        "total_withdrawn": str(w.total_withdrawn) if w else zero,
    }


class AdminDeliveryBoyService:

    @staticmethod
    def list_delivery_boys(db: Session, search: str = None, is_active: bool = None,
                           provider_id: str = None, approval_status: str = None,
                           page: int = 1, limit: int = 20):
        query = db.query(DeliveryBoy)
        if search:
            pattern = f"%{search}%"
            query = query.filter(DeliveryBoy.full_name.ilike(pattern) | DeliveryBoy.mobile_number.ilike(pattern))
        if is_active is not None:
            query = query.filter(DeliveryBoy.is_active == is_active)
        if provider_id:
            query = query.filter(DeliveryBoy.assigned_provider_reference_id == provider_id)
        if approval_status:
            if approval_status not in APPROVAL_STATUSES:
                raise DomainError(f"approval_status must be one of: {', '.join(APPROVAL_STATUSES)}")
            query = query.filter(DeliveryBoy.approval_status == approval_status)

        total = query.count()
        boys = query.order_by(DeliveryBoy.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
        return {"success": True, "total": total, "page": page, "delivery_boys": [delivery_boy_view(b) for b in boys]}

    @staticmethod
    def get_delivery_boy_detail(db: Session, delivery_boy_id: str):
        boy = _boy(db, delivery_boy_id)

        active_orders = db.query(Order).filter(
            Order.delivery_boy_reference_id == delivery_boy_id, Order.status.in_(ACTIVE_SUB_STATUSES)
        ).count() + db.query(ExtraOrder).filter(
            ExtraOrder.delivery_boy_reference_id == delivery_boy_id, ExtraOrder.status.in_(ACTIVE_EXTRA_STATUSES)
        ).count()
        delivered_total = db.query(Order).filter(
            Order.delivery_boy_reference_id == delivery_boy_id, Order.status == "delivered"
        ).count() + db.query(ExtraOrder).filter(
            ExtraOrder.delivery_boy_reference_id == delivery_boy_id, ExtraOrder.status == "delivered"
        ).count()

        documents = db.query(DeliveryBoyDocument).filter(
            DeliveryBoyDocument.delivery_boy_reference_id == delivery_boy_id
        ).all()
        payout = db.query(DeliveryBoyPayoutDetails).filter(
            DeliveryBoyPayoutDetails.delivery_boy_reference_id == delivery_boy_id
        ).first()

        return {
            "success": True,
            "delivery_boy": delivery_boy_view(boy),
            "documents": [_doc_view(d) for d in documents],
            "payout_details": payout_details_view(payout),
            "wallet": _wallet(db, delivery_boy_id),
            "stats": {"active_orders": active_orders, "total_delivered": delivered_total},
        }

    # ── Documents ─────────────────────────────────────────

    @staticmethod
    def document_file(db: Session, delivery_boy_id: str, document_id, admin_id: str, ip: str | None = None):
        doc = db.query(DeliveryBoyDocument).filter(
            DeliveryBoyDocument.delivery_boy_document_id == document_id,
            DeliveryBoyDocument.delivery_boy_reference_id == delivery_boy_id,
        ).first()
        if doc is None:
            raise DomainError("Document not found", 404)
        # viewing identity documents is itself an audited action
        record_audit(
            db, table="delivery.delivery_boy_documents", record_id=doc.delivery_boy_document_id,
            operation="U", old=None, new={"viewed_document": doc.document_type},
            actor_id=admin_id, actor_type="admin", ip=ip,
        )
        db.commit()
        return document_file_response(doc)

    @staticmethod
    def review_document(db: Session, delivery_boy_id: str, document_id, payload, admin_id: str, ip: str | None = None):
        doc = db.query(DeliveryBoyDocument).filter(
            DeliveryBoyDocument.delivery_boy_document_id == document_id,
            DeliveryBoyDocument.delivery_boy_reference_id == delivery_boy_id,
        ).with_for_update().first()
        if doc is None:
            raise DomainError("Document not found", 404)
        if payload.status == "rejected" and not payload.remarks:
            raise DomainError("Tell the partner why the document was rejected")

        before = _doc_view(doc)
        doc.status = payload.status
        doc.remarks = payload.remarks
        doc.verified_at = now_utc() if payload.status == "verified" else None
        doc.verified_by = admin_id if payload.status == "verified" else None
        record_audit(
            db, table="delivery.delivery_boy_documents", record_id=doc.delivery_boy_document_id,
            old=before, new=_doc_view(doc), actor_id=admin_id, actor_type="admin", ip=ip,
        )
        label = doc.document_type.replace("_", " ").title()
        notify.delivery_partner(
            db, delivery_boy_id, "document_review",
            f"{label} {payload.status}",
            f"Your {label} was {payload.status}." + (f" {payload.remarks}" if payload.remarks else ""),
            {"document_type": doc.document_type, "status": payload.status},
        )
        db.commit()
        return {"success": True, "message": f"Document {payload.status}", "document": _doc_view(doc)}

    # ── Approval ──────────────────────────────────────────

    @staticmethod
    def set_approval(db: Session, delivery_boy_id: str, *, approve: bool, note: str | None, admin_id: str, ip: str | None = None):
        boy = _boy(db, delivery_boy_id, lock=True)
        before = delivery_boy_view(boy)

        if approve:
            docs = {
                d.document_type: d.status
                for d in db.query(DeliveryBoyDocument).filter(
                    DeliveryBoyDocument.delivery_boy_reference_id == delivery_boy_id
                )
            }
            unverified = [t for t in DOCUMENT_TYPES if docs.get(t) != "verified"]
            if unverified:
                raise DomainError(f"Verify these documents first: {', '.join(unverified)}")
            if not (boy.full_name and boy.vehicle_type and boy.vehicle_number):
                raise DomainError("Personal and vehicle details are incomplete")
            payout = db.query(DeliveryBoyPayoutDetails).filter(
                DeliveryBoyPayoutDetails.delivery_boy_reference_id == delivery_boy_id
            ).first()
            if not payout or not (payout.upi_id or (payout.account_number and payout.ifsc_code)):
                raise DomainError("Payout details (UPI or bank account) are missing")
            boy.approval_status = "approved"
            boy.approval_note = note
            boy.approved_at = now_utc()
            boy.approved_by = admin_id
        else:
            if not note:
                raise DomainError("Give the partner a reason for the rejection")
            if _out_for_delivery(db, delivery_boy_id):
                raise DomainError("The partner is carrying orders right now; try again after they are delivered")
            boy.approval_status = "rejected"
            boy.approval_note = note
            boy.approved_at = None
            boy.approved_by = None
            boy.is_online = False
            _release_open_assignments(db, delivery_boy_id, reason="partner_rejected", admin_id=admin_id)

        record_audit(
            db, table="delivery.delivery_boys", record_id=boy.delivery_boy_id,
            old=before, new=delivery_boy_view(boy), actor_id=admin_id, actor_type="admin", ip=ip,
        )
        notify.delivery_partner(
            db, delivery_boy_id, "application",
            "Application approved" if approve else "Application not approved",
            "You can now go online and receive deliveries." if approve else note,
            {"approval_status": boy.approval_status},
        )
        db.commit()
        business_event("delivery_partner.approval", delivery_boy_id=delivery_boy_id, approved=approve, admin_id=admin_id)
        return {
            "success": True,
            "message": "Delivery partner approved" if approve else "Delivery partner rejected",
            "delivery_boy": delivery_boy_view(boy),
        }

    # ── Edit / activation ─────────────────────────────────

    @staticmethod
    def update_delivery_boy(db: Session, delivery_boy_id: str, payload, admin_id: str, ip: str | None = None):
        boy = _boy(db, delivery_boy_id, lock=True)
        before = delivery_boy_view(boy)
        update_data = payload.model_dump(exclude_unset=True)

        if update_data.get("is_active") is False and boy.is_active:
            pending = _out_for_delivery(db, delivery_boy_id)
            if pending:
                raise DomainError(f"Cannot deactivate: {pending} order(s) currently out for delivery.")
            boy.is_online = False
            revoke_sessions(boy)
            _release_open_assignments(db, delivery_boy_id, reason="partner_deactivated", admin_id=admin_id)
        if "vehicle_number" in update_data and update_data["vehicle_number"]:
            update_data["vehicle_number"] = update_data["vehicle_number"].upper()

        for key, value in update_data.items():
            setattr(boy, key, value)

        record_audit(
            db, table="delivery.delivery_boys", record_id=boy.delivery_boy_id,
            old=before, new=delivery_boy_view(boy), actor_id=admin_id, actor_type="admin", ip=ip,
        )
        db.commit()
        db.refresh(boy)
        return {"success": True, "message": "Delivery partner updated", "delivery_boy": delivery_boy_view(boy)}

    @staticmethod
    def assign_provider(db: Session, delivery_boy_id: str, provider_id: str | None, admin_id: str, ip: str | None = None):
        boy = _boy(db, delivery_boy_id, lock=True)
        if provider_id is not None:
            provider = db.query(Provider).filter(Provider.provider_id == provider_id).first()
            if not provider:
                raise DomainError("Provider not found", 404)
        before = delivery_boy_view(boy)
        boy.assigned_provider_reference_id = provider_id
        released = 0
        if provider_id is not None:
            # a dedicated partner only serves that kitchen's subscriptions
            released = release_partner_subscriptions(
                db, delivery_boy_id, reason="partner_moved_kitchen", actor_id=admin_id,
                actor_type="admin", keep_provider_id=provider_id,
            )
        record_audit(
            db, table="delivery.delivery_boys", record_id=boy.delivery_boy_id,
            old=before, new=delivery_boy_view(boy), actor_id=admin_id, actor_type="admin", ip=ip,
        )
        db.commit()
        return {
            "success": True,
            "message": ("Kitchen assigned to delivery partner" if provider_id else "Partner moved to the shared pool")
            + (f"; {released} subscription(s) of other kitchens were unassigned" if released else ""),
            "delivery_boy_id": delivery_boy_id,
            "assigned_provider_reference_id": provider_id,
            "subscriptions_unassigned": released,
        }

    @staticmethod
    def payout_details(db: Session, delivery_boy_id: str, admin_id: str, ip: str | None = None):
        _boy(db, delivery_boy_id)
        payout = db.query(DeliveryBoyPayoutDetails).filter(
            DeliveryBoyPayoutDetails.delivery_boy_reference_id == delivery_boy_id
        ).first()
        # full account number is needed to make the transfer; the view is audited
        record_audit(
            db, table="delivery.delivery_boy_payout_details", record_id=delivery_boy_id,
            new={"viewed": "payout_details"}, actor_id=admin_id, actor_type="admin", ip=ip,
        )
        db.commit()
        return {"success": True, "payout_details": payout_details_view(payout, reveal=True)}
