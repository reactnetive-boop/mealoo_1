from sqlalchemy.orm import Session

from app.repositories.service_unavailable_log_repository import (
    ServiceUnavailableLogRepository
)


class ServiceUnavailableLogService:

    @staticmethod
    def create_log(
        db: Session,
        data: dict
    ):

        return (
            ServiceUnavailableLogRepository
            .create_log(
                db=db,
                data=data
            )
        )