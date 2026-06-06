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
from app.api.v1.endpoints.user_auth import router as user_auth_router
from app.api.v1.endpoints.user_profile import router as user_profile_router
from app.api.v1.endpoints.user_address import router as user_address_router
from app.api.v1.endpoints.user_menu import router as user_menu_router
from app.api.v1.endpoints.user_order import router as user_order_router
from app.api.v1.endpoints.user_wallet import router as user_wallet_router
from app.api.v1.endpoints.user_subscription import router as user_subscription_router
from app.api.v1.endpoints.user_review import router as user_review_router
from app.api.v1.endpoints.user_complaint import router as user_complaint_router

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

api_router.include_router(
    user_auth_router,
    prefix="/user/auth",
    tags=["User Authentication"]
)

api_router.include_router(
    user_profile_router,
    prefix="/user",
    tags=["User Profile"]
)

api_router.include_router(
    user_address_router,
    prefix="/user",
    tags=["User Address"]
)

api_router.include_router(
    user_menu_router,
    prefix="/user/menu",
    tags=["User Menu"]
)

api_router.include_router(
    user_order_router,
    prefix="/user/order",
    tags=["User Order"]
)

api_router.include_router(
    user_wallet_router,
    prefix="/user/wallet",
    tags=["User Wallet"]
)

api_router.include_router(
    user_subscription_router,
    prefix="/user/subscription",
    tags=["User Subscription"]
)

api_router.include_router(
    user_review_router,
    prefix="/user/review",
    tags=["User Review"]
)

api_router.include_router(
    user_complaint_router,
    prefix="/user/complaint",
    tags=["User Complaint"]
)
