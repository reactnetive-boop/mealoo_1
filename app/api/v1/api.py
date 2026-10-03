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
from app.api.v1.endpoints.user_cart import router as user_cart_router
from app.api.v1.endpoints.user_wallet import router as user_wallet_router
from app.api.v1.endpoints.user_subscription import router as user_subscription_router
from app.api.v1.endpoints.user_review import router as user_review_router
from app.api.v1.endpoints.user_complaint import router as user_complaint_router
from app.api.v1.endpoints.provider_orders import router as provider_orders_router
from app.api.v1.endpoints.provider_wallet import router as provider_wallet_router
from app.api.v1.endpoints.delivery_auth import router as delivery_auth_router
from app.api.v1.endpoints.delivery_orders import router as delivery_orders_router
from app.api.v1.endpoints.delivery_account import router as delivery_account_router
from app.api.v1.endpoints.provider_complaint import router as provider_complaint_router
from app.api.v1.endpoints.delivery_complaint import router as delivery_complaint_router
from app.api.v1.endpoints.user_notification import router as user_notification_router
from app.api.v1.endpoints.user_payment import router as user_payment_router
from app.api.v1.endpoints.admin_auth import router as admin_auth_router
from app.api.v1.endpoints.admin_users import router as admin_users_router
from app.api.v1.endpoints.admin_providers import router as admin_providers_router
from app.api.v1.endpoints.admin_delivery_boys import router as admin_delivery_boys_router
from app.api.v1.endpoints.admin_packages import router as admin_packages_router
from app.api.v1.endpoints.admin_plans import router as admin_plans_router
from app.api.v1.endpoints.admin_complaints import router as admin_complaints_router
from app.api.v1.endpoints.admin_reviews import router as admin_reviews_router
from app.api.v1.endpoints.admin_orders import router as admin_orders_router
from app.api.v1.endpoints.admin_pincodes import router as admin_pincodes_router
from app.api.v1.endpoints.admin_dashboard import router as admin_dashboard_router
from app.api.v1.endpoints.admin_payments import router as admin_payments_router
from app.api.v1.endpoints.admin_pricing import router as admin_pricing_router
from app.api.v1.endpoints.admin_payouts import router as admin_payouts_router
from app.api.v1.endpoints.public_config import router as public_config_router

api_router = APIRouter()

# ── Public (no auth) ──────────────────────────────────────

api_router.include_router(public_config_router, prefix="/public", tags=["Public"])

# ── Provider ──────────────────────────────────────────────

api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["Provider Auth"]
)

api_router.include_router(
    provider.router,
    prefix="/provider",
    tags=["Provider"]
)

api_router.include_router(
    menu.router,
    prefix="/menu",
    tags=["Provider Menu"]
)

api_router.include_router(
    provider_selected_package_router,
    prefix="/provider-package",
    tags=["Provider Menu"]
)

api_router.include_router(package_item_router,  prefix="/package/item",
    tags=["Provider Package Item"]
)

api_router.include_router(package_image_router,  prefix="/package/image",
    tags=["Provider Package Image"]
)

api_router.include_router(
    provider_orders_router,
    prefix="/provider/orders",
    tags=["Provider Orders"]
)

api_router.include_router(
    provider_wallet_router,
    prefix="/provider/wallet",
    tags=["Provider Wallet"]
)

api_router.include_router(
    provider_complaint_router,
    prefix="/provider/complaint",
    tags=["Provider Complaint"]
)

# ── User ──────────────────────────────────────────────────

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
    location_router,
    prefix="/location",
    tags=["User Location"]
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
    user_cart_router,
    prefix="/user/cart",
    tags=["User Cart"]
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

api_router.include_router(
    user_notification_router,
    prefix="/user/notification",
    tags=["User Notification"]
)

api_router.include_router(
    user_payment_router,
    prefix="/user/payment",
    tags=["User Payment"]
)

# ── Delivery Boy ──────────────────────────────────────────

api_router.include_router(
    delivery_auth_router,
    prefix="/delivery/auth",
    tags=["Delivery Boy Auth"]
)

api_router.include_router(
    delivery_orders_router,
    prefix="/delivery",
    tags=["Delivery Boy"]
)

api_router.include_router(
    delivery_account_router,
    prefix="/delivery",
    tags=["Delivery Boy Account"]
)

api_router.include_router(
    delivery_complaint_router,
    prefix="/delivery/complaint",
    tags=["Delivery Boy Complaint"]
)

# ── Admin ─────────────────────────────────────────────────
api_router.include_router(admin_auth_router,          prefix="/admin/auth",          tags=["Admin Auth"])
api_router.include_router(admin_dashboard_router,     prefix="/admin/dashboard",     tags=["Admin Dashboard"])
api_router.include_router(admin_users_router,         prefix="/admin/users",         tags=["Admin — Users"])
api_router.include_router(admin_providers_router,     prefix="/admin/providers",     tags=["Admin — Providers"])
api_router.include_router(admin_delivery_boys_router, prefix="/admin/delivery-boys", tags=["Admin — Delivery Boys"])
api_router.include_router(admin_packages_router,      prefix="/admin/packages",      tags=["Admin — Packages"])
api_router.include_router(admin_plans_router,         prefix="/admin/plans",         tags=["Admin — Plans"])
api_router.include_router(admin_complaints_router,    prefix="/admin/complaints",    tags=["Admin — Complaints"])
api_router.include_router(admin_reviews_router,       prefix="/admin/reviews",       tags=["Admin — Reviews"])
api_router.include_router(admin_orders_router,        prefix="/admin/orders",        tags=["Admin — Orders"])
api_router.include_router(admin_pincodes_router,      prefix="/admin/pincodes",      tags=["Admin — Pincodes"])
api_router.include_router(admin_payments_router,      prefix="/admin/payments",      tags=["Admin — Payments"])
api_router.include_router(admin_pricing_router,       prefix="/admin/pricing",       tags=["Admin — Pricing"])
api_router.include_router(admin_payouts_router,       prefix="/admin/payouts",       tags=["Admin — Withdrawals"])
