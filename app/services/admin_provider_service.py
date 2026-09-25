from decimal import Decimal
from datetime import date as Date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.provider_model import Provider
from app.models.subscription_model import Subscription
from app.models.menu_package_model import MenuPackage
from app.models.provider_wallet_model import ProviderWallet
from app.models.provider_wallet_transaction_model import ProviderWalletTransaction
from app.models.provider_unavailability_model import ProviderUnavailability
from app.repositories.provider_wallet_repository import ProviderWalletRepository
from app.repositories.package_capacity_repository import PackageCapacityRepository


class AdminProviderService:

    @staticmethod
    def list_providers(db: Session, search: str = None, pincode: int = None,
                       is_profile_completed: bool = None, page: int = 1, limit: int = 20):
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

        total = query.count()
        providers = query.order_by(Provider.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
        return {"success": True, "total": total, "page": page, "providers": providers}

    @staticmethod
    def get_provider_detail(db: Session, provider_id: str):
        provider = db.query(Provider).filter(Provider.provider_id == provider_id).first()
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        packages = (
            db.query(MenuPackage)
            .filter(MenuPackage.provider_id == provider_id)
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
            "provider": provider,
            "packages": packages,
            "recent_subscriptions": subscriptions,
            "wallet": wallet,
            "recent_transactions": txns
        }

    @staticmethod
    def update_provider(db: Session, provider_id: str, payload):
        provider = db.query(Provider).filter(Provider.provider_id == provider_id).first()
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        update_data = payload.model_dump(exclude_unset=True)

        # a lowered daily limit must still cover meals already committed
        new_quota = update_data.get("daily_meal_quota")
        if new_quota is not None:
            PackageCapacityRepository.validate_provider_quota_reduction(
                db, provider_id, new_quota
            )

        for key, value in update_data.items():
            setattr(provider, key, value)
        db.commit()
        db.refresh(provider)

        return {"success": True, "message": "Provider updated", "provider": provider}

    @staticmethod
    def get_daily_quota_status(db: Session, provider_id: str, for_date: Date = None):
        provider = db.query(Provider).filter(Provider.provider_id == provider_id).first()
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        status = PackageCapacityRepository.get_provider_quota_status(
            db, provider_id, for_date or Date.today()
        )
        return {
            "success": True,
            "provider_id": provider.provider_id,
            "business_name": provider.business_name,
            **status
        }

    @staticmethod
    def set_provider_active(db: Session, provider_id: str, is_active: bool):
        provider = db.query(Provider).filter(Provider.provider_id == provider_id).first()
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        if not is_active:
            active_subs = db.query(Subscription).filter(
                Subscription.vendor_reference_id == provider_id,
                Subscription.status == "active"
            ).count()
            if active_subs:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot deactivate provider with {active_subs} active subscription(s)."
                )

        provider.is_active = is_active
        db.commit()
        action = "activated" if is_active else "deactivated"
        return {"success": True, "message": f"Provider {action}"}

    @staticmethod
    def toggle_accepting_orders(db: Session, provider_id: str, accepting: bool):
        provider = db.query(Provider).filter(Provider.provider_id == provider_id).first()
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")
        provider.is_accepting_orders = accepting
        db.commit()
        state = "now accepting orders" if accepting else "not accepting orders"
        return {"success": True, "message": f"Provider is {state}"}

    @staticmethod
    def mark_unavailable(db: Session, provider_id: str, payload):
        provider = db.query(Provider).filter(Provider.provider_id == provider_id).first()
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        existing = db.query(ProviderUnavailability).filter(
            ProviderUnavailability.provider_reference_id == provider_id,
            ProviderUnavailability.unavailable_date == payload.date
        ).first()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Provider is already marked unavailable on {payload.date}"
            )

        record = ProviderUnavailability(
            provider_reference_id=provider_id,
            unavailable_date=payload.date,
            reason=payload.reason,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return {"success": True, "message": f"Provider marked unavailable on {payload.date}", "record": record}

    @staticmethod
    def remove_unavailability(db: Session, provider_id: str, unavailable_date: Date):
        record = db.query(ProviderUnavailability).filter(
            ProviderUnavailability.provider_reference_id == provider_id,
            ProviderUnavailability.unavailable_date == unavailable_date
        ).first()
        if not record:
            raise HTTPException(status_code=404, detail="Unavailability record not found")
        db.delete(record)
        db.commit()
        return {"success": True, "message": f"Unavailability removed for {unavailable_date}"}

    @staticmethod
    def list_unavailability(db: Session, provider_id: str):
        provider = db.query(Provider).filter(Provider.provider_id == provider_id).first()
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")
        records = (
            db.query(ProviderUnavailability)
            .filter(ProviderUnavailability.provider_reference_id == provider_id)
            .order_by(ProviderUnavailability.unavailable_date.desc())
            .all()
        )
        return {"success": True, "total": len(records), "records": records}

    @staticmethod
    def adjust_wallet(db: Session, provider_id: str, payload, admin_id: str):
        if payload.type not in ("credit", "debit"):
            raise HTTPException(status_code=400, detail="type must be 'credit' or 'debit'")

        provider = db.query(Provider).filter(Provider.provider_id == provider_id).first()
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        amount = Decimal(str(payload.amount))
        wallet = ProviderWalletRepository.get_or_create(db, provider_id)
        balance_before = Decimal(str(wallet.balance))

        if payload.type == "debit" and amount > balance_before:
            raise HTTPException(status_code=400, detail=f"Insufficient balance. Available: ₹{balance_before}")

        if payload.type == "credit":
            ProviderWalletRepository.credit(db, wallet, amount)
        else:
            ProviderWalletRepository.debit(db, wallet, amount)

        ProviderWalletRepository.create_transaction(db, {
            "wallet_reference_id": wallet.provider_wallet_id,
            "provider_reference_id": provider_id,
            "type": payload.type,
            "reason": "manual_credit" if payload.type == "credit" else "adjustment",
            "amount": amount,
            "balance_before": balance_before,
            "balance_after": Decimal(str(wallet.balance)),
            "description": payload.reason,
        })
        db.commit()

        return {
            "success": True,
            "message": f"Provider wallet {payload.type}ed ₹{amount}",
            "balance_before": balance_before,
            "balance_after": Decimal(str(wallet.balance))
        }
