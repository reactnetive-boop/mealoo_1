from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.delivery_boy_model import DeliveryBoy
from app.models.order_model import Order
from app.models.extra_order_model import ExtraOrder


class AdminDeliveryBoyService:

    @staticmethod
    def list_delivery_boys(db: Session, search: str = None, is_active: bool = None,
                           provider_id: str = None, page: int = 1, limit: int = 20):
        query = db.query(DeliveryBoy)
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                DeliveryBoy.full_name.ilike(pattern) |
                DeliveryBoy.mobile_number.ilike(pattern)
            )
        if is_active is not None:
            query = query.filter(DeliveryBoy.is_active == is_active)
        if provider_id:
            query = query.filter(DeliveryBoy.assigned_provider_reference_id == provider_id)

        total = query.count()
        boys = query.order_by(DeliveryBoy.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
        return {"success": True, "total": total, "page": page, "delivery_boys": boys}

    @staticmethod
    def get_delivery_boy_detail(db: Session, delivery_boy_id: str):
        boy = db.query(DeliveryBoy).filter(DeliveryBoy.delivery_boy_id == delivery_boy_id).first()
        if not boy:
            raise HTTPException(status_code=404, detail="Delivery boy not found")

        active_orders = db.query(Order).filter(
            Order.delivery_boy_reference_id == delivery_boy_id,
            Order.status.in_(["scheduled", "preparing", "out_for_delivery"])
        ).count()

        delivered_total = db.query(Order).filter(
            Order.delivery_boy_reference_id == delivery_boy_id,
            Order.status == "delivered"
        ).count()

        return {
            "success": True,
            "delivery_boy": boy,
            "stats": {
                "active_orders": active_orders,
                "total_delivered": delivered_total
            }
        }

    @staticmethod
    def update_delivery_boy(db: Session, delivery_boy_id: str, payload):
        boy = db.query(DeliveryBoy).filter(DeliveryBoy.delivery_boy_id == delivery_boy_id).first()
        if not boy:
            raise HTTPException(status_code=404, detail="Delivery boy not found")

        update_data = payload.model_dump(exclude_unset=True)

        if "is_active" in update_data and not update_data["is_active"]:
            pending = db.query(Order).filter(
                Order.delivery_boy_reference_id == delivery_boy_id,
                Order.status.in_(["out_for_delivery"])
            ).count()
            if pending:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot deactivate: {pending} order(s) currently out for delivery."
                )

        for key, value in update_data.items():
            setattr(boy, key, value)
        db.commit()
        db.refresh(boy)

        return {"success": True, "message": "Delivery boy updated", "delivery_boy": boy}

    @staticmethod
    def assign_provider(db: Session, delivery_boy_id: str, provider_id: str):
        boy = db.query(DeliveryBoy).filter(DeliveryBoy.delivery_boy_id == delivery_boy_id).first()
        if not boy:
            raise HTTPException(status_code=404, detail="Delivery boy not found")

        boy.assigned_provider_reference_id = provider_id
        db.commit()

        return {
            "success": True,
            "message": "Provider assigned to delivery boy",
            "delivery_boy_id": delivery_boy_id,
            "assigned_provider_reference_id": provider_id
        }
