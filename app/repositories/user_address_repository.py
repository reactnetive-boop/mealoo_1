from sqlalchemy.orm import Session

from app.models.user_address_model import UserAddress


class UserAddressRepository:

    @staticmethod
    def get_by_id(
        db: Session,
        address_id
    ):

        return (
            db.query(UserAddress)
            .filter(
                UserAddress.user_address_id == address_id,
                UserAddress.is_active == True
            )
            .first()
        )

    @staticmethod
    def get_all_by_user(
        db: Session,
        user_id
    ):

        return (
            db.query(UserAddress)
            .filter(
                UserAddress.user_reference_id == user_id,
                UserAddress.is_active == True
            )
            .order_by(
                UserAddress.is_default.desc(),
                UserAddress.created_at.desc()
            )
            .all()
        )

    @staticmethod
    def count_by_user(
        db: Session,
        user_id
    ):

        return (
            db.query(UserAddress)
            .filter(
                UserAddress.user_reference_id == user_id,
                UserAddress.is_active == True
            )
            .count()
        )

    @staticmethod
    def unset_default(
        db: Session,
        user_id,
        exclude_address_id=None
    ):
        query = (
            db.query(UserAddress)
            .filter(
                UserAddress.user_reference_id == user_id,
                UserAddress.is_default == True,
                UserAddress.is_active == True
            )
        )

        if exclude_address_id:
            query = query.filter(
                UserAddress.user_address_id != exclude_address_id
            )

        query.update({"is_default": False}, synchronize_session=False)

    @staticmethod
    def create_address(
        db: Session,
        address_data: dict
    ):

        address = UserAddress(**address_data)

        db.add(address)

        db.commit()

        db.refresh(address)

        return address

    @staticmethod
    def update_address(
        db: Session,
        address: UserAddress,
        update_data: dict
    ):

        for key, value in update_data.items():

            setattr(
                address,
                key,
                value
            )

        db.commit()

        db.refresh(address)

        return address

    @staticmethod
    def delete_address(
        db: Session,
        address: UserAddress
    ):

        address.is_active = False

        db.commit()

        db.refresh(address)

        return address
