from app.repositories.pincode_repository import PincodeRepository
from app.services.service_unavailable_log_service import (
    ServiceUnavailableLogService
)

class PincodeService:

    @staticmethod
    def verify_pincode(
        db,
        pincode=None,
        request=None
    ):

        if request:
            pincode = request.pincode

        pincode_data = (
            PincodeRepository.get_pincode(
                db=db,
                pincode=pincode
            )
        )

        if not pincode_data:

            if request:

                ServiceUnavailableLogService.create_log(
                    db=db,
                    data={
                        "provider_id": (
                            request.provider_id
                        ),
                        "pincode": (
                            request.pincode
                        ),
                        "house_no": (
                            request.house_no
                        ),
                        "address": (
                            request.address
                        ),
                        "landmark": (
                            request.landmark
                        ),
                        "city": (
                            request.city
                        ),
                        "state": (
                            request.state
                        ),
                        "requested_from": (
                            "provider_app"
                        ),
                        "remarks": (
                            "Service not available"
                        )
                    }
                )

            return {
                "success": False,
                "serviceable": False,
                "message": (
                    "Service not available in this area"
                )
            }

        return {
            "success": True,
            "serviceable": True,
            "city": pincode_data.city,
            "state": pincode_data.state
        }
