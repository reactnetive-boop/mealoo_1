from pydantic import BaseModel


class VerifyPincodeRequest(BaseModel):
    provider_id: str | None = None

    pincode: int

    house_no: str | None = None

    address: str | None = None

    landmark: str | None = None

    city: str | None = None

    state: str | None = None

class VerifyPincodeResponse(BaseModel):
    success: bool
    serviceable: bool
    city: str | None = None
    state: str | None = None
    message: str | None = None