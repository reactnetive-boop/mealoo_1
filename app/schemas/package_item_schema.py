from pydantic import BaseModel, Field

from typing import Optional

from uuid import UUID


class AddPackageItemRequest(BaseModel):

    package_id: UUID
    item_name: str = Field(..., min_length=1, max_length=255)
    quantity: Optional[str] = Field(None, max_length=100)
    item_order: Optional[int] = Field(None, ge=0, le=1000)


class UpdatePackageItemRequest(BaseModel):

    item_name: Optional[str] = Field(None, min_length=1, max_length=255)
    quantity: Optional[str] = Field(None, max_length=100)
    item_order: Optional[int] = Field(None, ge=0, le=1000)


class PackageItemResponse(BaseModel):

    success: bool
    message: str
    item_id: UUID | None = None


class CommonResponse(BaseModel):

    success: bool
    message: str