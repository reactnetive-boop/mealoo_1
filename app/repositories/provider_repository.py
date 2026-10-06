from sqlalchemy.orm import Session

from app.models.provider_model import Provider


class ProviderRepository:

    @staticmethod
    def get_by_mobile(
        db: Session,
        mobile_number: str
    ):

        return (
            db.query(Provider)
            .filter(
                Provider.mobile_number == mobile_number
            )
            .first()
        )

    @staticmethod
    def get_by_provider_id(
        db: Session,
        provider_id
    ):

        return (
            db.query(Provider)
            .filter(
                Provider.provider_id == provider_id
            )
            .first()
        )

    @staticmethod
    def create_provider(
        db: Session,
        provider_data: dict
    ):

        provider = Provider(
            **provider_data
        )

        db.add(provider)

        db.flush()

        db.refresh(provider)

        return provider

    @staticmethod
    def update_provider(
        db: Session,
        provider: Provider,
        update_data: dict
    ):

        for key, value in update_data.items():

            setattr(
                provider,
                key,
                value
            )

        db.flush()

        db.refresh(provider)

        return provider

    @staticmethod
    def update_profile_image(
        db: Session,
        provider,
        profile_image: str
    ):

        provider.profile_image = profile_image

        db.flush()

        db.refresh(provider)

        return provider
        
    @staticmethod
    def update_provider_address(
        db,
        provider,
        request
    ):

        provider.house_no = request.house_no
        provider.address = request.address
        provider.landmark = request.landmark
        provider.city = request.city
        provider.state = request.state
        provider.pincode = request.pincode
        provider.is_profile_completed = True

        db.flush()
        db.refresh(provider)

        return provider