from pydantic import BaseModel


class VerifyPincodeRequest(BaseModel):
    pincode: int


class VerifyPincodeResponse(BaseModel):
    success: bool
    serviceable: bool
    city: str | None = None
    state: str | None = None
    message: str | None = None