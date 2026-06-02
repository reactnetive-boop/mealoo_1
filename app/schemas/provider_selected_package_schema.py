from uuid import UUID

from pydantic import BaseModel


class SelectPackageRequest(BaseModel):
    provider_id: UUID
    package_id: UUID


class SelectPackageResponse(BaseModel):
    success: bool
    message: str