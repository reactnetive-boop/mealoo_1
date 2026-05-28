from pydantic import BaseModel

from typing import Optional

from uuid import UUID


class AddPackageItemRequest(BaseModel):

    package_id: UUID
    item_name: str
    quantity: Optional[str] = None
    item_order: Optional[int] = 0


class UpdatePackageItemRequest(BaseModel):

    item_name: Optional[str] = None
    quantity: Optional[str] = None
    item_order: Optional[int] = None


class PackageItemResponse(BaseModel):

    success: bool
    message: str
    item_id: UUID | None = None


class CommonResponse(BaseModel):

    success: bool
    message: str