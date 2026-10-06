from sqlalchemy.orm import Session

from app.models.user_otp_log_model import UserOTPLog


class UserOTPRepository:

    @staticmethod
    def create_otp(
        db: Session,
        otp_data: dict
    ):

        otp_log = UserOTPLog(**otp_data)

        db.add(otp_log)

        db.flush()

        db.refresh(otp_log)

        return otp_log

    @staticmethod
    def get_latest_otp(
        db: Session,
        contact: str,
        purpose: str
    ):

        return (
            db.query(UserOTPLog)
            .filter(
                UserOTPLog.contact == contact,
                UserOTPLog.purpose == purpose,
                UserOTPLog.is_used == False
            )
            .order_by(
                UserOTPLog.created_at.desc()
            )
            .first()
        )
