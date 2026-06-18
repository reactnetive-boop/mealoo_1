from sqlalchemy.orm import Session

from app.models.user_model import User


class UserRepository:

    @staticmethod
    def get_by_phone(
        db: Session,
        phone: str
    ):

        return (
            db.query(User)
            .filter(
                User.phone == phone,
                User.deleted_at == None
            )
            .first()
        )

    @staticmethod
    def get_by_email(
        db: Session,
        email: str
    ):

        return (
            db.query(User)
            .filter(
                User.email == email,
                User.deleted_at == None
            )
            .first()
        )

    @staticmethod
    def get_by_user_id(
        db: Session,
        user_id: str
    ):

        return (
            db.query(User)
            .filter(
                User.user_id == user_id
            )
            .first()
        )

    @staticmethod
    def create_user(
        db: Session,
        user_data: dict
    ):

        user = User(**user_data)

        db.add(user)

        db.commit()

        db.refresh(user)

        return user

    @staticmethod
    def update_user(
        db: Session,
        user: User,
        update_data: dict
    ):

        for key, value in update_data.items():

            setattr(
                user,
                key,
                value
            )

        db.commit()

        db.refresh(user)

        return user

    @staticmethod
    def update_profile_image(
        db: Session,
        user: User,
        avatar_url: str
    ):

        user.avatar_url = avatar_url

        db.commit()

        db.refresh(user)

        return user
