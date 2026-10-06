
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.domain.status import EXTRA_OPEN_STATUSES
from app.models.extra_order_model import ExtraOrder
from app.models.subscription_model import Subscription
from app.repositories.user_address_repository import UserAddressRepository
from app.repositories.user_repository import UserRepository


def _address_in_use(db: Session, address_id) -> bool:
    if db.query(Subscription).filter(
        Subscription.user_address_reference_id == address_id,
        Subscription.status.in_(("active", "paused")),
    ).first():
        return True
    return db.query(ExtraOrder).filter(
        ExtraOrder.address_reference_id == address_id,
        ExtraOrder.status.in_(EXTRA_OPEN_STATUSES),
    ).first() is not None


class UserAddressService:

    @staticmethod
    def add_address(
        db: Session,
        user_id: str,
        payload
    ):

        existing_count = UserAddressRepository.count_by_user(db, user_id)
        is_first_address = existing_count == 0

        address_data = payload.model_dump()
        address_data["user_reference_id"] = user_id

        if is_first_address:
            address_data["is_default"] = True
        elif address_data.get("is_default"):
            UserAddressRepository.unset_default(db, user_id)

        address = UserAddressRepository.create_address(
            db,
            address_data
        )

        if is_first_address:
            user = UserRepository.get_by_user_id(db, user_id)
            if user and not user.is_profile_completed:
                UserRepository.update_user(
                    db,
                    user,
                    {"is_profile_completed": True}
                )
        # address and profile flag commit together
        db.commit()

        return {
            "success": True,
            "message": "Address added successfully",
            "address_id": str(address.user_address_id)
        }

    @staticmethod
    def get_address(
        db: Session,
        user_id: str,
        address_id: str
    ):

        address = UserAddressRepository.get_by_id(
            db,
            address_id
        )

        if not address:

            raise DomainError("Address not found", 404)

        if str(address.user_reference_id) != user_id:

            raise DomainError("Address not found", 404)

        return address

    @staticmethod
    def get_address_list(
        db: Session,
        user_id: str
    ):

        addresses = UserAddressRepository.get_all_by_user(
            db,
            user_id
        )

        return {
            "success": True,
            "total": len(addresses),
            "addresses": addresses
        }

    @staticmethod
    def update_address(
        db: Session,
        user_id: str,
        address_id: str,
        payload
    ):

        address = UserAddressRepository.get_by_id(
            db,
            address_id
        )

        if not address:

            raise DomainError("Address not found", 404)

        if str(address.user_reference_id) != user_id:

            raise DomainError("Address not found", 404)

        update_data = payload.model_dump(
            exclude_unset=True
        )

        # Kitchens are matched by pincode: moving an address that running
        # orders deliver to would send meals to a kitchen that does not serve it
        if (
            "pin_code" in update_data
            and update_data["pin_code"] != address.pin_code
            and _address_in_use(db, address.user_address_id)
        ):
            raise DomainError(
                "This address has running subscriptions or orders. Add a new address instead of "
                "changing its pincode."
            )

        if update_data.get("is_default"):
            # Unset all other defaults first (same transaction)
            UserAddressRepository.unset_default(
                db,
                user_id,
                exclude_address_id=address.user_address_id
            )

        updated_address = UserAddressRepository.update_address(
            db,
            address,
            update_data
        )
        db.commit()

        return {
            "success": True,
            "message": "Address updated successfully",
            "address_id": str(updated_address.user_address_id)
        }

    @staticmethod
    def delete_address(
        db: Session,
        user_id: str,
        address_id: str
    ):

        address = UserAddressRepository.get_by_id(
            db,
            address_id
        )

        if not address:

            raise DomainError("Address not found", 404)

        if str(address.user_reference_id) != user_id:

            raise DomainError("Address not found", 404)

        if _address_in_use(db, address.user_address_id):
            raise DomainError("This address has running subscriptions or orders and cannot be deleted yet")

        UserAddressRepository.delete_address(
            db,
            address
        )
        db.commit()

        # Keep exactly one default address
        if address.is_default:
            remaining = UserAddressRepository.get_all_by_user(db, user_id)
            if remaining:
                remaining[0].is_default = True
                db.commit()

        return {
            "success": True,
            "message": "Address deleted successfully"
        }
