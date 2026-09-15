from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.otp_log_model import OTPLog


class OTPRepository:

    @staticmethod
    def create_otp(
        db: Session,
        otp_data: dict
    ):

        otp_data.setdefault("created_at", datetime.now(timezone.utc))

        otp = OTPLog(**otp_data)

        db.add(otp)

        db.commit()

        db.refresh(otp)

        return otp
    
    @staticmethod
    def get_latest_otp(
        db: Session,
        mobile_number: str,
        purpose: str = None
    ):

        query = (
            db.query(OTPLog)
            .filter(
                OTPLog.mobile_number == mobile_number
            )
        )

        if purpose:

            query = query.filter(
                OTPLog.purpose == purpose
            )

        return (
            query
            .order_by(
                OTPLog.created_at.desc()
            )
            .first()
        )