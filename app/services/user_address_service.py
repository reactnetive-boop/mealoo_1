from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.repositories.user_address_repository import UserAddressRepository


class UserAddressService:

    @staticmethod
    def add_address(
        db: Session,
        user_id: str,
        payload
    ):

        if payload.is_default:

            UserAddressRepository.unset_default(
                db,
                user_id
            )

        address_data = payload.model_dump()
        address_data["user_id"] = user_id

        address = UserAddressRepository.create_address(
            db,
            address_data
        )

        return {
            "success": True,
            "message": "Address added successfully",
            "address_id": str(address.id)
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

        if str(address.user_id) != user_id:

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

        if str(address.user_id) != user_id:

            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )

        update_data = payload.model_dump(
            exclude_unset=True
        )

        if update_data.get("is_default"):

            UserAddressRepository.unset_default(
                db,
                user_id
            )

        updated_address = UserAddressRepository.update_address(
            db,
            address,
            update_data
        )

        return {
            "success": True,
            "message": "Address updated successfully",
            "address_id": str(updated_address.id)
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

        if str(address.user_id) != user_id:

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
