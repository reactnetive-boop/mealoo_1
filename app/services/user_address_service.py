from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.repositories.user_address_repository import UserAddressRepository
from app.repositories.user_repository import UserRepository


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

            raise HTTPException(
                status_code=404,
                detail="Address not found"
            )

        if str(address.user_reference_id) != user_id:

            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )

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

            raise HTTPException(
                status_code=404,
                detail="Address not found"
            )

        if str(address.user_reference_id) != user_id:

            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )

        update_data = payload.model_dump(
            exclude_unset=True
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

            raise HTTPException(
                status_code=404,
                detail="Address not found"
            )

        if str(address.user_reference_id) != user_id:

            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )

        UserAddressRepository.delete_address(
            db,
            address
        )

        return {
            "success": True,
            "message": "Address deleted successfully"
        }
