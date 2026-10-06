from app.repositories.pincode_repository import PincodeRepository
from app.services.service_unavailable_log_service import ServiceUnavailableLogService


class PincodeService:

    @staticmethod
    def verify_pincode(db, pincode=None, request=None):
        """
        Is this pincode served? An unserved pincode is a normal answer
        (success, serviceable=false), not an error. Requests from addresses we
        don't serve are logged so Orleeno can see where demand is.
        """
        if request:
            pincode = request.pincode
        pincode_data = PincodeRepository.get_pincode(db=db, pincode=pincode)

        if not pincode_data:
            if request:
                ServiceUnavailableLogService.create_log(
                    db=db,
                    data={
                        # never trust a caller-supplied kitchen id here
                        "provider_id": None,
                        "pincode": request.pincode,
                        "house_no": request.house_no,
                        "address": request.address,
                        "landmark": request.landmark,
                        "city": request.city,
                        "state": request.state,
                        "requested_from": "provider_app",
                        "remarks": "Service not available",
                    },
                )
                db.commit()
            return {
                "success": True,
                "serviceable": False,
                "message": "Service not available in this area",
            }

        return {
            "success": True,
            "serviceable": True,
            "city": pincode_data.city,
            "state": pincode_data.state,
        }
