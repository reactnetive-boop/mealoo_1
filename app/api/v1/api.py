from app.api.v1.endpoints import auth
from fastapi import APIRouter
from app.api.v1.endpoints import provider
from app.api.v1.endpoints import menu
from app.api.v1.endpoints.location import router as location_router
from app.api.v1.endpoints.package_item import router as package_item_router
from app.api.v1.endpoints.package_image import (
    router as package_image_router
)
from app.api.v1.endpoints.provider_selected_package_endpoint import router as provider_selected_package_router
api_router = APIRouter()

api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["Authentication"]
)

api_router.include_router(
    provider.router,
    prefix="/provider",
    tags=["Provider"]
)
api_router.include_router(
    menu.router,
    prefix="/menu",
    tags=["Menu"]
)
api_router.include_router(
    location_router,
    prefix="/location",
    tags=["Location"]
)

api_router.include_router(package_item_router,  prefix="/package/item",
    tags=["Package Item"]
)

api_router.include_router(package_image_router,  prefix="/package/image",
    tags=["Package Image"]
)
api_router.include_router(
    provider_selected_package_router,
    prefix="/provider-package",
    tags=["Provider"]
)
