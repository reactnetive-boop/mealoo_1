from sqlalchemy.orm import Session

from app.models.service_unavailable_log import (
    ServiceUnavailableLog
)


class ServiceUnavailableLogRepository:

    @staticmethod
    def create_log(
        db: Session,
        data: dict
    ):

        log = ServiceUnavailableLog(
            **data
        )

        db.add(log)

        db.commit()

        db.refresh(log)

        return log