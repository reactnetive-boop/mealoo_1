from pydantic import BaseModel

from typing import Optional

from uuid import UUID


class UploadPackageImageResponse(
    BaseModel
):

    success: bool
    message: str
    image_id: Optional[UUID] = None
    image_url: Optional[str] = None


class CommonResponse(
    BaseModel
):

    success: bool
    message: str