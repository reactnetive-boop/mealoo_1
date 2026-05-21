from app.api.v1.endpoints import auth
from fastapi import APIRouter
from app.api.v1.endpoints import provider

api_router = APIRouter()

api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["Authentication"]
)

api_router.include_router(
    provider.router,
    prefix="/provider",
    tags=["Authentication"]
)