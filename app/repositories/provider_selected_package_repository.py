from app.models.provider_selected_package_model import (
    ProviderSelectedPackage
)


class ProviderSelectedPackageRepository:

    @staticmethod
    def get_provider_package(
        db,
        provider_id,
        package_id
    ):
        return (
            db.query(
                ProviderSelectedPackage
            )
            .filter(
                ProviderSelectedPackage.provider_id
                == provider_id,

                ProviderSelectedPackage.package_id
                == package_id,

                ProviderSelectedPackage.is_active
                == True
            )
            .first()
        )

    @staticmethod
    def create(
        db,
        provider_id,
        package_id,
        daily_capacity: int = None,
    ):
        record = ProviderSelectedPackage(
            provider_id=provider_id,
            package_id=package_id,
            daily_capacity=daily_capacity,
        )

        db.add(record)
        db.commit()
        db.refresh(record)

        return record

    @staticmethod
    def update_capacity(
        db,
        provider_id,
        package_id,
        daily_capacity: int | None,
    ) -> ProviderSelectedPackage | None:
        """
        Update the daily_capacity for an active provider-package pair.
        Returns the updated record, or None if the pair doesn't exist.
        """
        record = (
            db.query(ProviderSelectedPackage)
            .filter(
                ProviderSelectedPackage.provider_id == provider_id,
                ProviderSelectedPackage.package_id == package_id,
                ProviderSelectedPackage.is_active == True,
            )
            .first()
        )

        if record is None:
            return None

        record.daily_capacity = daily_capacity
        db.commit()
        db.refresh(record)

        return record