from datetime import date as Date

from sqlalchemy.orm import Session

from app.core.audit import record_audit, business_event
from app.core.clock import now_utc, today_local
from app.core.errors import DomainError
from app.domain import capacity, ledger, notify
from app.domain.eligibility import assert_pincode_can_change, serviceable_pincode
from app.domain.pricing import money
from app.models.provider_model import Provider
from app.models.subscription_model import Subscription
from app.models.menu_package_model import MenuPackage
from app.models.provider_wallet_model import ProviderWallet
from app.models.provider_wallet_transaction_model import ProviderWalletTransaction
from app.models.provider_unavailability_model import ProviderUnavailability
from app.services.admin_views import provider_view, package_admin_view, subscription_admin_view
from app.services.auth_common import revoke_sessions
from app.services.provider_service import missing_profile_fields

APPROVAL_STATUSES = ("pending", "approved", "rejected")


def _provider(db: Session, provider_id, lock: bool = False) -> Provider:
    q = db.query(Provider).filter(Provider.provider_id == provider_id)
    if lock:
        q = q.with_for_update()
    provider = q.first()
    if not provider:
        raise DomainError("Provider not found", 404)
    return provider


def _open_subscription_count(db: Session, provider_id) -> int:
    return db.query(Subscription).filter(
        Subscription.vendor_reference_id == provider_id,
        Subscription.status.in_(("active", "paused")),
    ).count()


def _wallet_view(w) -> dict | None:
    if w is None:
        return None
    return {
        "provider_wallet_id": w.provider_wallet_id,
        "balance": w.balance,
        "total_earned": w.total_earned,
        "total_withdrawn": w.total_withdrawn,
    }


def _txn_view(t) -> dict:
    return {
        "provider_wallet_transaction_id": t.provider_wallet_transaction_id,
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


class AdminProviderService:

    @staticmethod
    def list_providers(db: Session, search: str = None, pincode: int = None,
                       is_profile_completed: bool = None, approval_status: str = None,
                       is_active: bool = None, page: int = 1, limit: int = 20):
        query = db.query(Provider)
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                Provider.full_name.ilike(pattern) |
                Provider.business_name.ilike(pattern) |
                Provider.mobile_number.ilike(pattern)
            )
        if pincode is not None:
            query = query.filter(Provider.pincode == pincode)
        if is_profile_completed is not None:
            query = query.filter(Provider.is_profile_completed == is_profile_completed)
        if approval_status:
            if approval_status not in APPROVAL_STATUSES:
                raise DomainError(f"approval_status must be one of: {', '.join(APPROVAL_STATUSES)}")
            query = query.filter(Provider.approval_status == approval_status)
        if is_active is not None:
            query = query.filter(Provider.is_active == is_active)

        total = query.count()
        providers = query.order_by(Provider.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
        return {"success": True, "total": total, "page": page, "providers": [provider_view(p) for p in providers]}

    @staticmethod
    def get_provider_detail(db: Session, provider_id: str):
        provider = _provider(db, provider_id)

        packages = (
            db.query(MenuPackage)
            .filter(MenuPackage.provider_id == provider_id, MenuPackage.is_predefined == False)  # noqa: E712
            .order_by(MenuPackage.created_at.desc())
            .all()
        )
        subscriptions = (
            db.query(Subscription)
            .filter(Subscription.vendor_reference_id == provider_id)
            .order_by(Subscription.created_at.desc())
            .limit(10)
            .all()
        )
        wallet = db.query(ProviderWallet).filter(ProviderWallet.provider_reference_id == provider_id).first()
        txns = (
            db.query(ProviderWalletTransaction)
            .filter(ProviderWalletTransaction.provider_reference_id == provider_id)
            .order_by(ProviderWalletTransaction.created_at.desc())
            .limit(20)
            .all()
        )

        return {
            "success": True,
            "provider": provider_view(provider),
            "missing_profile_fields": missing_profile_fields(provider),
            "packages": [package_admin_view(p) for p in packages],
            "recent_subscriptions": [subscription_admin_view(s) for s in subscriptions],
            "wallet": _wallet_view(wallet),
            "recent_transactions": [_txn_view(t) for t in txns],
        }

    # ── Approval ──────────────────────────────────────────

    @staticmethod
    def set_approval(db: Session, provider_id: str, *, approve: bool, note: str | None, admin_id: str, ip: str | None = None):
        provider = _provider(db, provider_id, lock=True)
        before = provider_view(provider)

        if approve:
            missing = missing_profile_fields(provider)
            if missing:
                raise DomainError(f"Kitchen profile is incomplete: {', '.join(missing)}")
            if not serviceable_pincode(db, provider.pincode):
                raise DomainError("The kitchen's pincode is not an active Orleeno service area")
            provider.approval_status = "approved"
            provider.approval_note = note
            provider.approved_at = now_utc()
            provider.approved_by = admin_id
        else:
            if not note:
                raise DomainError("Give the kitchen a reason for the rejection")
            if provider.approval_status == "approved" and _open_subscription_count(db, provider_id):
                raise DomainError(
                    "This kitchen has running subscriptions. Deactivate or move them before revoking approval."
                )
            provider.approval_status = "rejected"
            provider.approval_note = note
            provider.approved_at = None
            provider.approved_by = None

        record_audit(
            db, table="provider.providers", record_id=provider.provider_id,
            old=before, new=provider_view(provider), actor_id=admin_id, actor_type="admin", ip=ip,
        )
        if approve:
            notify.kitchen(
                db, provider.provider_id, "account_update", "Kitchen approved",
                "Your kitchen is live on Orleeno. Add packages and start accepting orders." + (f" {note}" if note else ""),
            )
        else:
            notify.kitchen(
                db, provider.provider_id, "account_update", "Application needs changes",
                f"Your kitchen application was not approved: {note} Update your profile and submit again.",
            )
        db.commit()
        business_event("provider.approval", provider_id=provider_id, approved=approve, admin_id=admin_id)
        return {
            "success": True,
            "message": "Kitchen approved" if approve else "Kitchen application rejected",
            "provider": provider_view(provider),
        }

    # ── Edit ──────────────────────────────────────────────

    @staticmethod
    def update_provider(db: Session, provider_id: str, payload, admin_id: str, ip: str | None = None):
        provider = _provider(db, provider_id, lock=True)
        before = provider_view(provider)
        update_data = payload.model_dump(exclude_unset=True)

        if "pincode" in update_data and update_data["pincode"] is not None:
            assert_pincode_can_change(db, provider, update_data["pincode"])
            if not serviceable_pincode(db, update_data["pincode"]):
                raise DomainError("That pincode is not an active Orleeno service area")

        # a lowered daily limit must still cover meals already committed
        if update_data.get("daily_meal_quota") is not None:
            peak = capacity.peak_future_demand(db, provider_id, today_local())
            if update_data["daily_meal_quota"] < peak:
                raise DomainError(
                    f"The kitchen already has {peak} meals booked for a single meal time; "
                    "the daily limit cannot be lower than that"
                )

        for key, value in update_data.items():
            setattr(provider, key, value)
        provider.is_profile_completed = not missing_profile_fields(provider)

        record_audit(
            db, table="provider.providers", record_id=provider.provider_id,
            old=before, new=provider_view(provider), actor_id=admin_id, actor_type="admin", ip=ip,
        )
        db.commit()
        db.refresh(provider)
        return {"success": True, "message": "Provider updated", "provider": provider_view(provider)}

    @staticmethod
    def get_daily_quota_status(db: Session, provider_id: str, for_date: Date = None):
        provider = _provider(db, provider_id)
        status = capacity.quota_status(db, provider_id, for_date or today_local())
        return {
            "success": True,
            "provider_id": provider.provider_id,
            "business_name": provider.business_name,
            **status,
        }

    @staticmethod
    def set_provider_active(db: Session, provider_id: str, is_active: bool, admin_id: str, ip: str | None = None):
        provider = _provider(db, provider_id, lock=True)
        before = provider_view(provider)

        if not is_active:
            open_subs = _open_subscription_count(db, provider_id)
            if open_subs:
                raise DomainError(
                    f"Cannot deactivate a kitchen with {open_subs} running subscription(s). "
                    "Stop new orders (accepting-orders) and move or cancel those subscriptions first."
                )
            # deactivation also signs the kitchen out everywhere
            revoke_sessions(provider)

        provider.is_active = is_active
        record_audit(
            db, table="provider.providers", record_id=provider.provider_id,
            old=before, new=provider_view(provider), actor_id=admin_id, actor_type="admin", ip=ip,
        )
        notify.kitchen(
            db, provider.provider_id, "account_update",
            "Kitchen reactivated" if is_active else "Kitchen deactivated",
            "Your kitchen account is active again." if is_active
            else "Orleeno has deactivated your kitchen account. Contact support for details.",
        )
        db.commit()
        return {"success": True, "message": f"Provider {'activated' if is_active else 'deactivated'}"}

    @staticmethod
    def toggle_accepting_orders(db: Session, provider_id: str, accepting: bool, admin_id: str, ip: str | None = None):
        provider = _provider(db, provider_id, lock=True)
        before = provider_view(provider)
        provider.is_accepting_orders = accepting
        record_audit(
            db, table="provider.providers", record_id=provider.provider_id,
            old=before, new=provider_view(provider), actor_id=admin_id, actor_type="admin", ip=ip,
        )
        notify.kitchen(
            db, provider.provider_id, "account_update",
            "New orders turned on" if accepting else "New orders paused",
            "Orleeno turned new orders back on for your kitchen." if accepting
            else "Orleeno paused new orders for your kitchen. Running subscriptions continue as usual.",
        )
        db.commit()
        state = "now accepting orders" if accepting else "not accepting new orders"
        return {"success": True, "message": f"Provider is {state}"}

    # ── Holidays ──────────────────────────────────────────

    @staticmethod
    def mark_unavailable(db: Session, provider_id: str, payload, admin_id: str, ip: str | None = None):
        _provider(db, provider_id)
        if payload.date < today_local():
            raise DomainError("Holidays cannot be added for past dates")

        existing = db.query(ProviderUnavailability).filter(
            ProviderUnavailability.provider_reference_id == provider_id,
            ProviderUnavailability.unavailable_date == payload.date
        ).first()
        if existing:
            raise DomainError(f"Provider is already marked unavailable on {payload.date}", 409)

        record = ProviderUnavailability(
            provider_reference_id=provider_id,
            unavailable_date=payload.date,
            reason=payload.reason,
        )
        db.add(record)
        record_audit(
            db, table="provider.provider_unavailability", record_id=provider_id, operation="I",
            new={"date": payload.date, "reason": payload.reason}, actor_id=admin_id, actor_type="admin", ip=ip,
        )
        notify.kitchen(
            db, provider_id, "holiday", "Holiday added by Orleeno",
            f"Your kitchen is marked closed on {payload.date}."
            + (f" Reason: {payload.reason}." if payload.reason else "")
            + " Orders for that day will be moved or refunded.",
            {"date": str(payload.date)},
        )
        db.commit()
        db.refresh(record)
        return {
            "success": True,
            "message": (
                f"Provider marked unavailable on {payload.date}. Reassign that day's orders to another "
                "kitchen; anything left at the cut-off is cancelled and refunded automatically."
            ),
            "record": {
                "provider_unavailability_id": record.provider_unavailability_id,
                "unavailable_date": record.unavailable_date,
                "reason": record.reason,
            },
        }

    @staticmethod
    def remove_unavailability(db: Session, provider_id: str, unavailable_date: Date, admin_id: str, ip: str | None = None):
        record = db.query(ProviderUnavailability).filter(
            ProviderUnavailability.provider_reference_id == provider_id,
            ProviderUnavailability.unavailable_date == unavailable_date
        ).first()
        if not record:
            raise DomainError("Unavailability record not found", 404)
        if unavailable_date < today_local():
            raise DomainError("Past holidays cannot be removed")
        db.delete(record)
        record_audit(
            db, table="provider.provider_unavailability", record_id=provider_id, operation="D",
            old={"date": unavailable_date, "reason": record.reason}, actor_id=admin_id, actor_type="admin", ip=ip,
        )
        db.commit()
        return {"success": True, "message": f"Unavailability removed for {unavailable_date}"}

    @staticmethod
    def list_unavailability(db: Session, provider_id: str):
        _provider(db, provider_id)
        records = (
            db.query(ProviderUnavailability)
            .filter(ProviderUnavailability.provider_reference_id == provider_id)
            .order_by(ProviderUnavailability.unavailable_date.desc())
            .all()
        )
        return {
            "success": True,
            "total": len(records),
            "records": [
                {
                    "provider_unavailability_id": r.provider_unavailability_id,
                    "unavailable_date": r.unavailable_date,
                    "reason": r.reason,
                    "created_at": r.created_at,
                }
                for r in records
            ],
        }

    # ── Money ─────────────────────────────────────────────

    @staticmethod
    def adjust_wallet(db: Session, provider_id: str, payload, admin_id: str, idempotency_key: str, ip: str | None = None):
        if payload.type not in ("credit", "debit"):
            raise DomainError("type must be 'credit' or 'debit'")
        _provider(db, provider_id)

        amount = money(payload.amount)
        txn = ledger.post_provider(
            db, provider_id,
            type=payload.type, amount=amount,
            reason="manual_credit" if payload.type == "credit" else "adjustment",
            idempotency_key=f"admin_adjust:provider:{idempotency_key}",
            reference_type="admin_adjustment",
            description=payload.reason if not payload.description else f"{payload.reason} - {payload.description}",
        )
        # The platform funds a manual credit and recovers a manual debit
        ledger.post_platform(
            db, entry_type="manual_adjustment",
            direction="debit" if payload.type == "credit" else "credit",
            amount=amount, reference_type="provider_wallet_transaction",
            reference_id=txn.provider_wallet_transaction_id,
            idempotency_key=f"platform:admin_adjust:provider:{idempotency_key}",
            description=payload.reason,
        )
        record_audit(
            db, table="provider.provider_wallet_transactions", record_id=txn.provider_wallet_transaction_id,
            operation="I", new={"provider_id": provider_id, "type": payload.type, "amount": amount, "reason": payload.reason},
            actor_id=admin_id, actor_type="admin", ip=ip,
        )
        notify.kitchen(
            db, provider_id, "wallet", f"Wallet {payload.type}ed",
            f"Orleeno {payload.type}ed Rs {amount} {'to' if payload.type == 'credit' else 'from'} your wallet: {payload.reason}.",
            {"provider_wallet_transaction_id": str(txn.provider_wallet_transaction_id)},
        )
        db.commit()
        business_event("wallet.admin_adjust", owner="provider", owner_id=provider_id, type=payload.type, amount=amount, admin_id=admin_id)
        return {
            "success": True,
            "message": f"Provider wallet {payload.type}ed Rs {amount}",
            "balance_before": txn.balance_before,
            "balance_after": txn.balance_after,
        }
