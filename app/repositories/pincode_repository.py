from sqlalchemy.orm import Session

from app.models.serviceable_pincode_model import ServiceablePincode


class PincodeRepository:

    @staticmethod
    def get_pincode(db: Session, pincode: int):

        return (
            db.query(ServiceablePincode)
            .filter(
                ServiceablePincode.pincode == pincode,
                ServiceablePincode.is_active == True
            )
            .first()
        )