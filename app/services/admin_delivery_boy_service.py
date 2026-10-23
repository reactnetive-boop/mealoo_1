from sqlalchemy.orm import Session

from app.core.audit import record_audit, business_event
from app.core.clock import now_utc
from app.core.errors import DomainError
from app.domain import notify, vendor_partner
from app.domain.delivery_assignment import release_partner_subscriptions
from app.domain.status import (
    SUB_OPEN_STATUSES, EXTRA_OPEN_STATUSES, SUB_UNPICKED_STATUSES, EXTRA_UNPICKED_STATUSES, IN_HAND_STATUSES,
)
from app.models.delivery_boy_model import DeliveryBoy
from app.models.delivery_boy_wallet_model import DeliveryBoyWallet
from app.models.delivery_boy_wallet_transaction_model import DeliveryBoyWalletTransaction
from app.models.delivery_boy_document_model import DeliveryBoyDocument
from app.models.delivery_boy_payout_model import DeliveryBoyPayoutDetails
from app.models.delivery_partner_vendor_model import DeliveryPartnerVendor
from app.models.admin_user_model import AdminUser
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


def _kitchen_status(p: Provider) -> str:
    if not p.is_active:
        return "inactive"
    if p.approval_status != "approved":
        return "not_approved"
    if not p.is_accepting_orders:
        return "not_accepting_orders"
    return "active"


def _vendor_view(row: DeliveryPartnerVendor, p: Provider, open_tasks: int = 0, assigned_by: str | None = None) -> dict:
    return {
        "assignment_id": row.assignment_id,
        "provider_id": p.provider_id,
        "business_name": p.business_name,
        "owner_name": p.full_name,
        "mobile_number": p.mobile_number,
        "address": vendor_partner.kitchen_address(p),
        "area": p.area,
        "city": p.city,
        "pincode": p.pincode,
        "kitchen_status": _kitchen_status(p),
        "assignment_status": row.status,
        "assigned_at": row.assigned_at,
        "assigned_by_type": row.assigned_by_type,
        "assigned_by_name": assigned_by,
        "note": row.note,
        "ended_at": row.ended_at,
        "end_reason": row.end_reason,
        "open_tasks": open_tasks,
    }


def _vendors_of(db: Session, delivery_boy_id, include_history: bool = False) -> dict:
    q = (
        db.query(DeliveryPartnerVendor, Provider)
        .join(Provider, Provider.provider_id == DeliveryPartnerVendor.provider_reference_id)
        .filter(DeliveryPartnerVendor.delivery_boy_reference_id == delivery_boy_id)
    )
    if not include_history:
        q = q.filter(DeliveryPartnerVendor.status == "active")
    rows = q.order_by(DeliveryPartnerVendor.assigned_at.desc()).limit(200).all()
    admins = {
        a.admin_user_id: (a.full_name or a.email)
        for a in db.query(AdminUser).filter(
            AdminUser.admin_user_id.in_([r.assigned_by for r, _ in rows if r.assigned_by])
        )
    } if any(r.assigned_by for r, _ in rows) else {}
    active = [(r, p) for r, p in rows if r.status == "active"]
    tasks = vendor_partner.open_task_counts(db, delivery_boy_id, [p.provider_id for _, p in active])
    return {
        "assigned_vendor_count": len(active),
        "assigned_vendors": [
            _vendor_view(r, p, tasks.get(p.provider_id, 0), admins.get(r.assigned_by)) for r, p in active
        ],
        "vendor_history": [
            _vendor_view(r, p, 0, admins.get(r.assigned_by)) for r, p in rows if r.status != "active"
        ][:50],
    }


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
            query = query.filter(DeliveryBoy.delivery_boy_id.in_(
                db.query(DeliveryPartnerVendor.delivery_boy_reference_id).filter(
                    DeliveryPartnerVendor.provider_reference_id == provider_id,
                    DeliveryPartnerVendor.status == "active",
                )
            ))
        if approval_status:
            if approval_status not in APPROVAL_STATUSES:
                raise DomainError(f"approval_status must be one of: {', '.join(APPROVAL_STATUSES)}")
            query = query.filter(DeliveryBoy.approval_status == approval_status)

        total = query.count()
        boys = query.order_by(DeliveryBoy.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
        kitchens = vendor_partner.kitchens_by_partner(db, (b.delivery_boy_id for b in boys))
        rows = []
        for b in boys:
            mine = kitchens.get(b.delivery_boy_id, [])
            rows.append({
                **delivery_boy_view(b),
                "assigned_vendor_count": len(mine),
                "assigned_vendors": [
                    {"provider_id": p.provider_id, "business_name": p.business_name, "area": p.area}
                    for _, p in mine
                ],
            })
        return {"success": True, "total": total, "page": page, "delivery_boys": rows}

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
        txns = (
            db.query(DeliveryBoyWalletTransaction)
            .filter(DeliveryBoyWalletTransaction.delivery_boy_reference_id == delivery_boy_id)
            .order_by(DeliveryBoyWalletTransaction.created_at.desc())
            .limit(50)
            .all()
        )

        return {
            "success": True,
            "delivery_boy": delivery_boy_view(boy),
            **_vendors_of(db, delivery_boy_id, include_history=True),
            "documents": [_doc_view(d) for d in documents],
            "payout_details": payout_details_view(payout),
            "wallet": _wallet(db, delivery_boy_id),
            # every credit says which delivery it pays for (reference_type / reference_id)
            "recent_transactions": [
                {
                    "delivery_boy_wallet_transaction_id": t.delivery_boy_wallet_transaction_id,
                    "type": t.type,
                    "reason": t.reason,
                    "amount": t.amount,
                    "balance_before": t.balance_before,
                    "balance_after": t.balance_after,
                    "reference_type": t.reference_type,
                    "reference_id": t.reference_id,
                    "description": t.description,
                    "created_at": t.created_at,
                }
                for t in txns
            ],
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

    # ── Kitchens served (one partner, many kitchens; one current partner per kitchen) ──

    @staticmethod
    def list_vendors(db: Session, delivery_boy_id: str):
        _boy(db, delivery_boy_id)
        return {"success": True, "delivery_boy_id": delivery_boy_id, **_vendors_of(db, delivery_boy_id, include_history=True)}

    @staticmethod
    def add_vendor(db: Session, delivery_boy_id: str, provider_id, admin_id: str, note: str | None = None,
                   ip: str | None = None):
        boy = _boy(db, delivery_boy_id, lock=True)
        provider = db.query(Provider).filter(Provider.provider_id == provider_id).with_for_update().first()
        if provider is None:
            raise DomainError("Provider not found", 404)
        summary = vendor_partner.assign_kitchen(db, boy, provider, actor_id=admin_id, note=note, ip=ip)
        db.commit()
        name = provider.business_name or "Kitchen"
        if summary["action"] == "unchanged":
            message = f"{name} is already assigned to this partner"
        elif summary["action"] == "moved":
            message = f"{name} moved to {boy.full_name or 'this partner'}"
        else:
            message = f"{name} assigned to {boy.full_name or 'this partner'}"
        work = summary["subscriptions_assigned"] + summary["one_time_orders_assigned"]
        if work:
            message += f"; {summary['subscriptions_assigned']} subscription(s) and " \
                       f"{summary['one_time_orders_assigned']} one-time order(s) now go to them"
        if summary["kept_with_previous_partner"]:
            message += f"; {summary['kept_with_previous_partner']} already picked up stay with the previous partner"
        return {
            "success": True, "message": message, **summary,
            **_vendors_of(db, delivery_boy_id),
        }

    @staticmethod
    def remove_vendor(db: Session, delivery_boy_id: str, provider_id, admin_id: str, reason: str | None = None,
                      ip: str | None = None):
        boy = _boy(db, delivery_boy_id, lock=True)
        summary = vendor_partner.remove_kitchen(db, boy, provider_id, actor_id=admin_id, reason=reason, ip=ip)
        db.commit()
        released = summary["subscriptions_unassigned"] + summary["orders_unassigned"]
        return {
            "success": True,
            "message": "Kitchen removed from the partner"
            + (f"; {released} open subscription(s) / order(s) now need a partner" if released else ""),
            **summary,
            **_vendors_of(db, delivery_boy_id),
        }

    @staticmethod
    def assign_provider(db: Session, delivery_boy_id: str, provider_id: str | None, admin_id: str, ip: str | None = None):
        """
        Older admin builds: `provider_id` adds that kitchen to the partner (their
        other kitchens are kept); no `provider_id` removes all their kitchens
        (shared pool).
        """
        if provider_id is not None:
            return AdminDeliveryBoyService.add_vendor(db, delivery_boy_id, provider_id, admin_id, ip=ip)
        boy = _boy(db, delivery_boy_id, lock=True)
        removed = 0
        for row in vendor_partner.partner_rows(db, boy.delivery_boy_id, lock=True):
            vendor_partner.remove_kitchen(
                db, boy, row.provider_reference_id, actor_id=admin_id, reason="moved_to_shared_pool", ip=ip,
            )
            removed += 1
        db.commit()
        return {
            "success": True,
            "message": f"Partner moved to the shared pool; {removed} kitchen(s) removed",
            "delivery_boy_id": delivery_boy_id,
            "assigned_vendor_count": 0,
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
