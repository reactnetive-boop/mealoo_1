from app.api.v1.endpoints import auth
from fastapi import APIRouter
from app.api.v1.endpoints import provider
from app.api.v1.endpoints import menu
from app.api.v1.endpoints.location_endpoint import router as location_router
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