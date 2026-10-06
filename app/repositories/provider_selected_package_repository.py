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
    def get_capacities_for_provider(
        db,
        provider_id
    ) -> dict[str, int | None]:
        """
        Map of package_id -> daily_capacity for every active selection of
        this provider. None means no limit.
        """
        rows = (
            db.query(
                ProviderSelectedPackage.package_id,
                ProviderSelectedPackage.daily_capacity
            )
            .filter(
                ProviderSelectedPackage.provider_id == provider_id,
                ProviderSelectedPackage.is_active == True
            )
            .all()
        )

        return {str(r.package_id): r.daily_capacity for r in rows}

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
        db.flush()
        db.refresh(record)

        return record
