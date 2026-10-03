"""
Admin pricing configuration.

Components are versioned: an update never edits a row, it supersedes the
current version and inserts the next one. Orders keep the snapshot they were
priced with, so a change only affects checkouts after it.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit import record_audit, business_event
from app.core.clock import now_utc
from app.domain.pricing import build_quote, current_components, PARTNER_PAYOUT_KEY
from app.models.pricing_component_model import PricingComponent


def _view(c: PricingComponent) -> dict:
    return {
        "pricing_component_id": c.pricing_component_id,
        "component_key": c.component_key,
        "label": c.label,
        "calc_type": c.calc_type,
        "value": c.value,
        "applies_to": c.applies_to,
        "charge_basis": c.charge_basis,
        "is_customer_facing": bool(c.is_customer_facing),
        "is_active": bool(c.is_active),
        "version": c.version,
        "effective_from": c.effective_from,
        "superseded_at": c.superseded_at,
        "created_by": c.created_by,
        "change_reason": c.change_reason,
    }


class AdminPricingService:

    @staticmethod
    def current(db: Session):
        components = current_components(db)
        return {
            "success": True,
            "components": [_view(c) for c in components],
            "notes": {
                "percentage": "Percentages apply to the food amount (base price x meals - plan discount).",
                "per_unit": "Fixed amount for every meal unit (meals x quantity).",
                "per_delivery": "Fixed amount for every delivery drop.",
                "per_order": "Fixed amount once per checkout.",
                PARTNER_PAYOUT_KEY: "Internal cost paid to the delivery partner per delivery; never shown to customers.",
            },
        }

    @staticmethod
    def history(db: Session, component_key: str | None = None, limit: int = 100):
        q = db.query(PricingComponent)
        if component_key:
            q = q.filter(PricingComponent.component_key == component_key)
        rows = q.order_by(PricingComponent.component_key, PricingComponent.version.desc()).limit(limit).all()
        return {"success": True, "total": len(rows), "versions": [_view(r) for r in rows]}

    @staticmethod
    def update(db: Session, component_key: str, payload, admin_id: str, ip: str | None = None):
        current = (
            db.query(PricingComponent)
            .filter(PricingComponent.component_key == component_key, PricingComponent.superseded_at.is_(None))
            .with_for_update()
            .first()
        )
        if current is None:
            raise HTTPException(status_code=404, detail="Unknown pricing component")

        now = now_utc()
        current.superseded_at = now
        db.flush()

        new = PricingComponent(
            component_key=current.component_key,
            label=payload.label or current.label,
            calc_type=payload.calc_type,
            value=payload.value,
            applies_to=payload.applies_to,
            charge_basis=payload.charge_basis,
            # whether a component is charged to the customer is fixed per component
            is_customer_facing=current.is_customer_facing,
            is_active=payload.is_active,
            version=current.version + 1,
            effective_from=now,
            created_by=admin_id,
            change_reason=payload.change_reason,
        )
        db.add(new)
        db.flush()
        record_audit(
            db, table="master.pricing_components", record_id=new.pricing_component_id, operation="I",
            old=_view(current), new=_view(new), actor_id=admin_id, actor_type="admin", ip=ip,
        )
        db.commit()
        business_event("pricing.updated", key=component_key, version=new.version, admin_id=admin_id)
        return {
            "success": True,
            "message": f"{new.label} updated (version {new.version}). Applies to checkouts from now on; "
                       "existing subscriptions and orders keep their price.",
            "component": _view(new),
        }

    @staticmethod
    def preview(db: Session, payload):
        snapshot = build_quote(
            current_components(db),
            kind=payload.kind,
            base_unit_price=payload.base_unit_price,
            quantity=payload.quantity,
            deliveries=payload.deliveries,
            discount_percent=payload.discount_percent,
        )
        return {"success": True, "quote": snapshot}
