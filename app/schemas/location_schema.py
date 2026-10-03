from pydantic import BaseModel, Field


class VerifyPincodeRequest(BaseModel):
    # Ignored: an unauthenticated caller cannot speak for a kitchen. Kept so
    # older app versions that still send it are not rejected.
    provider_id: str | None = Field(None, max_length=64)

    pincode: int = Field(..., ge=100000, le=999999)

    house_no: str | None = Field(None, max_length=100)

    address: str | None = Field(None, max_length=500)

    landmark: str | None = Field(None, max_length=256)

    city: str | None = Field(None, max_length=128)

    state: str | None = Field(None, max_length=128)


class VerifyPincodeResponse(BaseModel):
    success: bool
    serviceable: bool
    city: str | None = None
    state: str | None = None
    message: str | None = None
