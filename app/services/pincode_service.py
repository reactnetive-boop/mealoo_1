from app.repositories.pincode_repository import PincodeRepository


class PincodeService:

    @staticmethod
    def verify_pincode(db, pincode: int):

        pincode_data = PincodeRepository.get_pincode(
            db=db,
            pincode=pincode
        )

        if not pincode_data:
            return {
                "success": False,
                "serviceable": False,
                "message": "Service not available in this area"
            }

        return {
            "success": True,
            "serviceable": True,
            "city": pincode_data.city,
            "state": pincode_data.state
        }