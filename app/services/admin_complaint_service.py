"""
Admin view of complaints raised from the three apps.

Customers, kitchens and delivery partners each have their own complaint table.
`_KINDS` describes them once, so listing, detail and resolution are written a
single time. The combined list is one SQL UNION ALL, sorted and paged in the
database.
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable

from sqlalchemy import func, literal, select, union_all
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.clock import now_utc
from app.core.config import COMPLAINT_SLA_HOURS
from app.models.admin_user_model import AdminUser
from app.core.errors import DomainError
from app.domain import notify
from app.models.complaint_model import Complaint
from app.models.delivery_boy_complaint_model import DeliveryBoyComplaint
from app.models.provider_complaint_model import ProviderComplaint

VALID_RESOLUTIONS = ("in_progress", "resolved", "rejected", "closed")
FINAL_STATUSES = ("resolved", "closed", "rejected")
OPEN_STATUSES = ("open", "in_progress")


def _ageing(row: dict) -> dict:
    """Hours since the complaint was raised, and whether it is past the SLA while still open."""
    created = row.get("created_at")
    age = round((now_utc() - created).total_seconds() / 3600, 1) if created else None
    row["age_hours"] = age
    row["overdue"] = bool(age is not None and row["status"] in OPEN_STATUSES and age > COMPLAINT_SLA_HOURS)
    return row


@dataclass(frozen=True)
class _Kind:
    model: type
    pk: str
    owner: str               # column with the complainant's id
    table: str               # audit table name
    label: str               # for "not found" messages
    notify: Callable


_KINDS = {
    "user": _Kind(Complaint, "complaint_id", "user_reference_id",
                  "provider.complaints", "User complaint", notify.customer),
    "provider": _Kind(ProviderComplaint, "provider_complaint_id", "provider_reference_id",
                      "provider.provider_complaints", "Provider complaint", notify.kitchen),
    "delivery_boy": _Kind(DeliveryBoyComplaint, "delivery_boy_complaint_id", "delivery_boy_reference_id",
                          "delivery.delivery_boy_complaints", "Delivery boy complaint", notify.delivery_partner),
}


def _kind(complainant_type: str) -> _Kind:
    try:
        return _KINDS[complainant_type]
    except KeyError:
        raise DomainError(f"complaint_type must be one of: {', '.join(_KINDS)}") from None


class AdminComplaintService:

    @staticmethod
    def list_all_complaints(db: Session, complaint_type: str = None, status: str = None,
                            against: str = None, page: int = 1, limit: int = 20,
                            assigned_to: str | None = None, overdue: bool | None = None):
        names = [complaint_type] if complaint_type else list(_KINDS)
        selects = []
        for name in names:
            kind = _kind(name)
            m = kind.model
            q = select(
                getattr(m, kind.pk).label("id"),
                literal(name).label("complainant_type"),
                getattr(m, kind.owner).label("complainant_id"),
                m.against.label("against"),
                m.status.label("status"),
                m.subject.label("subject"),
                m.assigned_to.label("assigned_to"),
                m.created_at.label("created_at"),
            )
            if status:
                q = q.where(m.status == status)
            if against:
                q = q.where(m.against == against)
            if assigned_to == "unassigned":
                q = q.where(m.assigned_to.is_(None))
            elif assigned_to:
                q = q.where(m.assigned_to == uuid.UUID(str(assigned_to)))
            if overdue:
                cutoff = now_utc() - timedelta(hours=COMPLAINT_SLA_HOURS)
                q = q.where(m.status.in_(OPEN_STATUSES), m.created_at < cutoff)
            selects.append(q)

        combined = (union_all(*selects) if len(selects) > 1 else selects[0]).subquery()
        total = db.scalar(select(func.count()).select_from(combined))
        rows = db.execute(
            select(combined)
            .order_by(combined.c.created_at.desc().nulls_last(), combined.c.id)
            .offset((page - 1) * limit)
            .limit(limit)
        ).mappings().all()
        return {
            "success": True,
            "total": total,
            "sla_hours": COMPLAINT_SLA_HOURS,
            "complaints": [_ageing(dict(r)) for r in rows],
        }

    @staticmethod
    def get(db: Session, complainant_type: str, complaint_id: str):
        kind = _kind(complainant_type)
        complaint = db.query(kind.model).filter(getattr(kind.model, kind.pk) == complaint_id).first()
        if not complaint:
            raise DomainError(f"{kind.label} not found", 404)
        return complaint

    @staticmethod
    def resolve(db: Session, complainant_type: str, complaint_id: str, payload, admin_id: str):
        if payload.status not in VALID_RESOLUTIONS:
            raise DomainError(f"Invalid status. Use one of: {', '.join(VALID_RESOLUTIONS)}")
        kind = _kind(complainant_type)
        complaint = (
            db.query(kind.model)
            .filter(getattr(kind.model, kind.pk) == complaint_id)
            .with_for_update()
            .first()
        )
        if not complaint:
            raise DomainError("Complaint not found", 404)
        if complaint.status in FINAL_STATUSES:
            raise DomainError(f"Complaint is already '{complaint.status}'")

        complaint.status = payload.status
        complaint.assigned_to = complaint.assigned_to or admin_id  # whoever acts first owns it
        if payload.admin_notes:
            complaint.admin_notes = payload.admin_notes
        if payload.resolution:
            complaint.resolution = payload.resolution
        if payload.status in FINAL_STATUSES:
            complaint.resolved_by = admin_id
            complaint.resolved_at = now_utc()

        pk = getattr(complaint, kind.pk)
        record_audit(
            db, table=kind.table, record_id=pk,
            new={"status": payload.status, "resolution": payload.resolution},
            actor_id=admin_id, actor_type="admin",
        )
        body = f"Your complaint '{complaint.subject}' is now '{payload.status}'."
        if payload.resolution:
            body += f" {payload.resolution}"
        kind.notify(
            db, getattr(complaint, kind.owner), "complaint_update", "Complaint update", body,
            {"complaint_id": str(pk), "status": payload.status},
        )
        db.commit()
        return {"success": True, "message": f"Complaint status updated to '{payload.status}'"}

    @staticmethod
    def assign(db: Session, complainant_type: str, complaint_id: str, assignee_id, admin_id: str,
               ip: str | None = None):
        kind = _kind(complainant_type)
        complaint = (
            db.query(kind.model).filter(getattr(kind.model, kind.pk) == complaint_id).with_for_update().first()
        )
        if not complaint:
            raise DomainError("Complaint not found", 404)
        if complaint.status in FINAL_STATUSES:
            raise DomainError(f"Complaint is already '{complaint.status}'")
        if assignee_id is not None:
            assignee = db.query(AdminUser).filter(
                AdminUser.admin_user_id == assignee_id, AdminUser.is_active == True  # noqa: E712
            ).first()
            if assignee is None:
                raise DomainError("Admin not found or inactive", 404)
        before = complaint.assigned_to
        complaint.assigned_to = assignee_id
        record_audit(
            db, table=kind.table, record_id=getattr(complaint, kind.pk),
            old={"assigned_to": before}, new={"assigned_to": assignee_id}, actor_id=admin_id, actor_type="admin", ip=ip,
        )
        db.commit()
        return {"success": True, "message": "Complaint assigned" if assignee_id else "Complaint unassigned"}
