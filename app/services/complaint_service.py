
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.core.paging import FIRST_PAGE, Paging
from app.models.extra_order_model import ExtraOrder
from app.models.order_model import Order
from app.models.subscription_model import Subscription
from app.repositories.complaint_repository import ComplaintRepository

# Statuses that allow user edits
EDITABLE_STATUSES = {"open"}


class ComplaintService:

    @staticmethod
    def raise_complaint(
        db: Session,
        user_id: str,
        payload
    ):

        complaint_data = payload.model_dump()

        # Schema field names → renamed model columns
        complaint_data["vendor_reference_id"] = complaint_data.pop("vendor_id", None)
        complaint_data["order_reference_id"] = complaint_data.pop("order_id", None)
        complaint_data["subscription_reference_id"] = complaint_data.pop("subscription_id", None)
        complaint_data["subscription_order_reference_id"] = complaint_data.pop("subscription_order_id", None)

        complaint_data["user_reference_id"] = user_id

        # Linked order / subscription must be the customer's own; the kitchen
        # is derived from it rather than trusted from the request
        if complaint_data["order_reference_id"]:
            order = db.query(ExtraOrder).filter(
                ExtraOrder.extra_order_id == complaint_data["order_reference_id"],
                ExtraOrder.user_reference_id == user_id,
            ).first()
            if order is None:
                raise DomainError("Order not found", 404)
            complaint_data["vendor_reference_id"] = order.vendor_reference_id
        if complaint_data["subscription_order_reference_id"]:
            meal = db.query(Order).filter(
                Order.order_id == complaint_data["subscription_order_reference_id"],
                Order.user_reference_id == user_id,
            ).first()
            if meal is None:
                raise DomainError("Meal not found", 404)
            if (
                complaint_data["subscription_reference_id"]
                and str(complaint_data["subscription_reference_id"]) != str(meal.subscription_reference_id)
            ):
                raise DomainError("The meal does not belong to that subscription")
            complaint_data["subscription_reference_id"] = meal.subscription_reference_id
        if complaint_data["subscription_reference_id"]:
            sub = db.query(Subscription).filter(
                Subscription.subscription_id == complaint_data["subscription_reference_id"],
                Subscription.user_reference_id == user_id,
            ).first()
            if sub is None:
                raise DomainError("Subscription not found", 404)
            complaint_data["vendor_reference_id"] = sub.vendor_reference_id
        elif complaint_data["vendor_reference_id"] and not complaint_data["order_reference_id"]:
            ordered = db.query(Subscription).filter(
                Subscription.user_reference_id == user_id,
                Subscription.vendor_reference_id == complaint_data["vendor_reference_id"],
            ).first() or db.query(ExtraOrder).filter(
                ExtraOrder.user_reference_id == user_id,
                ExtraOrder.vendor_reference_id == complaint_data["vendor_reference_id"],
            ).first()
            if not ordered:
                raise DomainError("You can only complain about kitchens you have ordered from")

        complaint_data["status"] = "open"

        complaint = ComplaintRepository.create(
            db, complaint_data
        )
        db.commit()

        return {
            "success": True,
            "message": "Complaint raised successfully",
            "complaint_id": str(complaint.complaint_id)
        }

    @staticmethod
    def get_my_complaints(db: Session, user_id: str, paging: Paging = FIRST_PAGE):
        complaints = ComplaintRepository.get_all_by_user(db, user_id, paging.offset, paging.limit)
        return {
            "success": True,
            **paging.meta(ComplaintRepository.count_by_user(db, user_id)),
            "complaints": complaints,
        }

    @staticmethod
    def get_complaint(
        db: Session,
        user_id: str,
        complaint_id
    ):

        complaint = ComplaintRepository.get_by_id(
            db, complaint_id
        )

        if not complaint:

            raise DomainError("Complaint not found", 404)

        if str(complaint.user_reference_id) != user_id:

            raise DomainError("Complaint not found", 404)

        return complaint

    @staticmethod
    def update_complaint(
        db: Session,
        user_id: str,
        complaint_id,
        payload
    ):

        complaint = ComplaintRepository.get_by_id(
            db, complaint_id
        )

        if not complaint:

            raise DomainError("Complaint not found", 404)

        if str(complaint.user_reference_id) != user_id:

            raise DomainError("Complaint not found", 404)

        if complaint.status not in EDITABLE_STATUSES:

            raise DomainError(f"Complaint cannot be edited. "
                    f"Current status: {complaint.status}", 400)

        update_data = payload.model_dump(exclude_unset=True)

        updated = ComplaintRepository.update(
            db, complaint, update_data
        )
        db.commit()

        return {
            "success": True,
            "message": "Complaint updated successfully",
            "complaint_id": str(updated.complaint_id)
        }

    @staticmethod
    def withdraw_complaint(
        db: Session,
        user_id: str,
        complaint_id
    ):

        complaint = ComplaintRepository.get_by_id(
            db, complaint_id
        )

        if not complaint:

            raise DomainError("Complaint not found", 404)

        if str(complaint.user_reference_id) != user_id:

            raise DomainError("Complaint not found", 404)

        if complaint.status not in EDITABLE_STATUSES:

            raise DomainError(f"Complaint cannot be withdrawn. "
                    f"Current status: {complaint.status}", 400)

        ComplaintRepository.withdraw(db, complaint)
        db.commit()

        return {
            "success": True,
            "message": "Complaint withdrawn successfully"
        }
