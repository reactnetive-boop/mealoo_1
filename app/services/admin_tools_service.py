"""
Admin tools: the audit-log viewer, menu categories, admin accounts,
broadcast notifications and delivery partner wallet adjustments.
"""

import re
from datetime import date, datetime, time

from sqlalchemy import func, insert, literal, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import push
from app.core.audit import business_event, record_audit, security_event
from app.core.clock import BUSINESS_TZ
from app.core.errors import DomainError
from app.core.security import hash_password
from app.domain import ledger, notify
from app.domain.pricing import money
from app.models.admin_user_model import AdminUser
from app.models.audit_log_model import AuditLog
from app.models.delivery_boy_model import DeliveryBoy
from app.models.delivery_boy_notification_model import DeliveryBoyNotification
from app.models.device_push_token_model import DevicePushToken
from app.models.menu_category_model import MenuCategory
from app.models.menu_package_model import MenuPackage
from app.models.notification_model import Notification
from app.models.provider_model import Provider
from app.models.provider_notification_model import ProviderNotification
from app.models.user_model import User
from app.services.auth_common import revoke_sessions

ADMIN_ROLES = ("super_admin", "moderator")


def _day_bounds(start: date | None, end: date | None):
    lo = datetime.combine(start, time.min, BUSINESS_TZ) if start else None
    hi = datetime.combine(end, time.max, BUSINESS_TZ) if end else None
    return lo, hi


# ── Audit log (AD-06) ─────────────────────────────────────────

class AuditLogService:

    @staticmethod
    def search(db: Session, *, table: str | None, record_id=None, actor_id=None, actor_type: str | None,
               operation: str | None, date_from: date | None, date_to: date | None, page: int, limit: int) -> dict:
        q = db.query(AuditLog)
        if table:
            q = q.filter(AuditLog.table_name == table)
        if record_id:
            q = q.filter(AuditLog.record_id == record_id)
        if actor_id:
            q = q.filter(AuditLog.changed_by == actor_id)
        if actor_type:
            q = q.filter(AuditLog.changed_by_type == actor_type)
        if operation:
            q = q.filter(AuditLog.operation == operation)
        lo, hi = _day_bounds(date_from, date_to)
        if lo:
            q = q.filter(AuditLog.created_at >= lo)
        if hi:
            q = q.filter(AuditLog.created_at <= hi)
        total = q.count()
        rows = q.order_by(AuditLog.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

        admin_ids = {r.changed_by for r in rows if r.changed_by_type == "admin" and r.changed_by}
        names = dict(
            db.query(AdminUser.admin_user_id, AdminUser.email).filter(AdminUser.admin_user_id.in_(admin_ids)).all()
        ) if admin_ids else {}
        return {
            "success": True,
            "total": total,
            "page": page,
            "logs": [
                {
                    "audit_log_id": r.audit_log_id,
                    "table": r.table_name,
                    "record_id": r.record_id,
                    "operation": r.operation,
                    "old": r.old_data,
                    "new": r.new_data,
                    "actor_id": r.changed_by,
                    "actor_type": r.changed_by_type,
                    "actor_name": names.get(r.changed_by),
                    "ip": str(r.ip_address) if r.ip_address else None,
                    "created_at": r.created_at,
                }
                for r in rows
            ],
        }

    @staticmethod
    def tables(db: Session) -> dict:
        rows = db.query(AuditLog.table_name, func.count()).group_by(AuditLog.table_name).order_by(AuditLog.table_name).all()
        return {"success": True, "tables": [{"table": t, "entries": n} for t, n in rows]}


# ── Menu categories ───────────────────────────────────────────

def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:150] or "category"


def _category_view(c: MenuCategory, packages: int = 0) -> dict:
    return {
        "category_id": c.category_id,
        "category_name": c.category_name,
        "category_slug": c.category_slug,
        "description": c.description,
        "display_order": c.display_order,
        "is_active": bool(c.is_active),
        "packages": packages,
        "created_at": c.created_at,
    }


class CategoryAdminService:

    @staticmethod
    def list(db: Session) -> dict:
        counts = dict(
            db.query(MenuPackage.category_reference_id, func.count())
            .filter(MenuPackage.deleted_at.is_(None))
            .group_by(MenuPackage.category_reference_id)
            .all()
        )
        rows = db.query(MenuCategory).order_by(MenuCategory.display_order, MenuCategory.category_name).all()
        return {"success": True, "categories": [_category_view(c, counts.get(c.category_id, 0)) for c in rows]}

    @staticmethod
    def create(db: Session, payload, admin_id: str, ip: str | None) -> dict:
        category = MenuCategory(
            category_name=payload.category_name.strip(),
            category_slug=_slug(payload.category_name),
            description=payload.description,
            display_order=payload.display_order or 0,
            is_active=True,
        )
        db.add(category)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise DomainError("A category with this name already exists", 409) from None
        record_audit(db, table="master.menu_categories", record_id=category.category_id, operation="I",
                     new=_category_view(category), actor_id=admin_id, actor_type="admin", ip=ip)
        db.commit()
        return {"success": True, "message": "Category created", "category": _category_view(category)}

    @staticmethod
    def update(db: Session, category_id, payload, admin_id: str, ip: str | None) -> dict:
        category = db.query(MenuCategory).filter(MenuCategory.category_id == category_id).with_for_update().first()
        if category is None:
            raise DomainError("Category not found", 404)
        before = _category_view(category)
        data = payload.model_dump(exclude_unset=True)
        if data.get("is_active") is False:
            in_use = db.query(MenuPackage).filter(
                MenuPackage.category_reference_id == category.category_id, MenuPackage.deleted_at.is_(None)
            ).count()
            if in_use:
                raise DomainError(f"{in_use} package(s) use this category. Move them to another category first.")
        if "category_name" in data:
            data["category_name"] = data["category_name"].strip()
            data["category_slug"] = _slug(data["category_name"])
        for key, value in data.items():
            setattr(category, key, value)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise DomainError("A category with this name already exists", 409) from None
        record_audit(db, table="master.menu_categories", record_id=category.category_id, old=before,
                     new=_category_view(category), actor_id=admin_id, actor_type="admin", ip=ip)
        db.commit()
        return {"success": True, "message": "Category updated", "category": _category_view(category)}


# ── Admin accounts ────────────────────────────────────────────

def _admin_view(a: AdminUser) -> dict:
    return {
        "admin_user_id": a.admin_user_id,
        "full_name": a.full_name,
        "email": a.email,
        "role": a.role,
        "is_active": bool(a.is_active),
        "two_factor_enabled": bool(a.totp_enabled),
        "last_login_at": a.last_login_at,
        "created_at": a.created_at,
    }


def _active_super_admins(db: Session) -> int:
    return db.query(AdminUser).filter(AdminUser.role == "super_admin", AdminUser.is_active == True).count()  # noqa: E712


class AdminAccountService:

    @staticmethod
    def list(db: Session) -> dict:
        rows = db.query(AdminUser).order_by(AdminUser.created_at).all()
        return {"success": True, "admins": [_admin_view(a) for a in rows]}

    @staticmethod
    def create(db: Session, payload, actor_id: str, ip: str | None) -> dict:
        email = payload.email.strip().lower()
        if db.query(AdminUser).filter(func.lower(AdminUser.email) == email).first():
            raise DomainError("An admin with this email already exists", 409)
        admin = AdminUser(
            full_name=payload.full_name.strip(), email=email, password_hash=hash_password(payload.password),
            role=payload.role, is_active=True,
        )
        db.add(admin)
        db.flush()
        record_audit(db, table="master.admin_users", record_id=admin.admin_user_id, operation="I",
                     new=_admin_view(admin), actor_id=actor_id, actor_type="admin", ip=ip)
        db.commit()
        security_event("admin.created", admin_id=admin.admin_user_id, role=admin.role, by=actor_id)
        return {"success": True, "message": "Admin created. Share the password privately; they should change it.",
                "admin": _admin_view(admin)}

    @staticmethod
    def update(db: Session, admin_id, payload, actor_id: str, ip: str | None) -> dict:
        admin = db.query(AdminUser).filter(AdminUser.admin_user_id == admin_id).with_for_update().first()
        if admin is None:
            raise DomainError("Admin not found", 404)
        data = payload.model_dump(exclude_unset=True)
        demoting = data.get("role", admin.role) != "super_admin" or data.get("is_active") is False
        if str(admin.admin_user_id) == str(actor_id) and demoting:
            raise DomainError("You cannot remove your own super_admin access")
        if admin.role == "super_admin" and admin.is_active and demoting and _active_super_admins(db) <= 1:
            raise DomainError("There must always be at least one active super_admin")
        before = _admin_view(admin)
        for key, value in data.items():
            setattr(admin, key, value)
        if data.get("is_active") is False or ("role" in data and data["role"] != before["role"]):
            revoke_sessions(admin)  # new rights apply from the next login
        record_audit(db, table="master.admin_users", record_id=admin.admin_user_id, old=before,
                     new=_admin_view(admin), actor_id=actor_id, actor_type="admin", ip=ip)
        db.commit()
        security_event("admin.updated", admin_id=admin.admin_user_id, by=actor_id, changes=list(data))
        return {"success": True, "message": "Admin updated", "admin": _admin_view(admin)}


# ── Broadcast notifications ───────────────────────────────────

# audience -> (push owner type, id column, notification model, its id column, its owner column, "active" rule)
_AUDIENCES = {
    "customers": ("customer", User.user_id, Notification, "notification_id", "user_reference_id",
                  User.status == "active"),
    "kitchens": ("provider", Provider.provider_id, ProviderNotification, "provider_notification_id",
                 "provider_reference_id", Provider.is_active == True),  # noqa: E712
    "partners": ("delivery_boy", DeliveryBoy.delivery_boy_id, DeliveryBoyNotification, "delivery_boy_notification_id",
                 "delivery_boy_reference_id", DeliveryBoy.is_active == True),  # noqa: E712
}


class BroadcastService:

    @staticmethod
    def send(db: Session, payload, admin_id: str, ip: str | None) -> dict:
        audiences = list(_AUDIENCES) if payload.audience == "everyone" else [payload.audience]
        data = {"broadcast": True}
        counts = {}
        for name in audiences:
            owner_type, id_col, note_model, note_id, owner_col, active = _AUDIENCES[name]
            recipients = select(id_col).where(active)
            # one INSERT ... SELECT for the whole audience
            result = db.execute(insert(note_model).from_select(
                [note_id, owner_col, "type", "title", "body", "data", "is_read"],
                select(
                    func.gen_random_uuid(), id_col, literal("announcement"), literal(payload.title),
                    literal(payload.body), literal(data, type_=note_model.__table__.c.data.type), literal(False),
                ).where(active),
            ))
            counts[name] = result.rowcount or 0
            owners = db.execute(
                select(DevicePushToken.owner_id).where(
                    DevicePushToken.owner_type == owner_type, DevicePushToken.owner_id.in_(recipients)
                ).distinct()
            ).scalars().all()
            for owner_id in owners:
                push.queue(db, owner_type, owner_id, payload.title, payload.body, {**data, "type": "announcement"})
        record_audit(db, table="broadcast", operation="I",
                     new={"audience": payload.audience, "title": payload.title, "recipients": counts},
                     actor_id=admin_id, actor_type="admin", ip=ip)
        db.commit()
        business_event("broadcast.sent", audience=payload.audience, recipients=sum(counts.values()), admin_id=admin_id)
        return {"success": True, "message": f"Sent to {sum(counts.values())} account(s)", "recipients": counts}


# ── Delivery partner wallet ───────────────────────────────────

class PartnerWalletAdminService:

    @staticmethod
    def adjust(db: Session, delivery_boy_id, payload, admin_id: str, idempotency_key: str, ip: str | None) -> dict:
        boy = db.query(DeliveryBoy).filter(DeliveryBoy.delivery_boy_id == delivery_boy_id).first()
        if boy is None:
            raise DomainError("Delivery partner not found", 404)
        amount = money(payload.amount)
        txn = ledger.post_delivery(
            db, boy.delivery_boy_id, type=payload.type, amount=amount,
            reason="manual_credit" if payload.type == "credit" else "adjustment",
            idempotency_key=f"admin_adjust:delivery_boy:{idempotency_key}",
            reference_type="admin_adjustment",
            description=payload.reason if not payload.description else f"{payload.reason} - {payload.description}",
        )
        ledger.post_platform(
            db, entry_type="manual_adjustment", direction="debit" if payload.type == "credit" else "credit",
            amount=amount, reference_type="partner_wallet_transaction",
            reference_id=txn.delivery_boy_wallet_transaction_id,
            idempotency_key=f"platform:admin_adjust:delivery_boy:{idempotency_key}", description=payload.reason,
        )
        record_audit(
            db, table="delivery.delivery_boy_wallet_transactions", record_id=txn.delivery_boy_wallet_transaction_id,
            operation="I", new={"delivery_boy_id": boy.delivery_boy_id, "type": payload.type, "amount": amount,
                                "reason": payload.reason},
            actor_id=admin_id, actor_type="admin", ip=ip,
        )
        notify.delivery_partner(
            db, boy.delivery_boy_id, "wallet", f"Wallet {payload.type}ed",
            f"Orleeno {payload.type}ed Rs {amount} {'to' if payload.type == 'credit' else 'from'} your wallet: "
            f"{payload.reason}.",
            {"delivery_boy_wallet_transaction_id": str(txn.delivery_boy_wallet_transaction_id)},
        )
        db.commit()
        business_event("wallet.admin_adjust", owner="delivery_boy", owner_id=boy.delivery_boy_id,
                       type=payload.type, amount=amount, admin_id=admin_id)
        return {
            "success": True,
            "message": f"Partner wallet {payload.type}ed Rs {amount}",
            "balance_before": txn.balance_before,
            "balance_after": txn.balance_after,
        }
