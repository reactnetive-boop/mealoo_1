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
        package_id
    ):
        record = (
            ProviderSelectedPackage(
                provider_id=provider_id,
                package_id=package_id
            )
        )

        db.add(record)
        db.commit()
        db.refresh(record)

        return record