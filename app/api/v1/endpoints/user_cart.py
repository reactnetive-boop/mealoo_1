from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.schemas.cart_schema import (
    AddToCartRequest,
    AddToCartResponse,
    CartResponse,
    RemoveFromCartResponse,
    ClearCartResponse,
    UpdateCartItemRequest,
)
from app.services.cart_service import CartService

router = APIRouter()


@router.post(
    "",
    response_model=AddToCartResponse,
    summary="Add Package to Cart",
    description=(
        "**Add a meal package to the user's cart.**\n\n"
        "Send `package_id` (UUID from package listing) and `quantity` (1–10). "
        "If the same package is already in the cart, its quantity is updated instead of creating a duplicate.\n\n"
        "**When to call:** When the user taps 'Add to Cart' on a package detail screen.\n\n"
        "**Flow:** `GET /user/menu/packages` → `GET /user/menu/packages/{id}` → "
        "`POST /user/cart` → `GET /user/cart` → proceed to subscribe"
    )
)
def add_to_cart(
    payload: AddToCartRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return CartService.add_to_cart(db, current_user["user_id"], payload)


@router.get(
    "",
    response_model=CartResponse,
    summary="View Cart",
    description=(
        "**Fetch all items currently in the user's cart with pricing summary.**\n\n"
        "Returns each cart item with package name, unit price, discounted price, quantity, "
        "item total, and the cart grand total.\n\n"
        "**When to call:** When the user opens the cart screen or before checkout.\n\n"
        "**Flow:** `POST /user/cart` → `GET /user/cart` → review → `POST /user/subscription`"
    )
)
def view_cart(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return CartService.get_cart(db, current_user["user_id"])


@router.put(
    "/{cart_item_id}",
    response_model=AddToCartResponse,
    summary="Update Cart Item Quantity",
    description=(
        "**Change the quantity of an existing cart item.**\n\n"
        "Send the new `quantity` (1–10). Use `cart_item_id` from the `GET /user/cart` response.\n\n"
        "**When to call:** When the user taps + / – on a cart item."
    )
)
def update_cart_item(
    cart_item_id: UUID,
    payload: UpdateCartItemRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return CartService.update_cart_item(
        db,
        current_user["user_id"],
        str(cart_item_id),
        payload,
    )


@router.delete(
    "/clear",
    response_model=ClearCartResponse,
    summary="Clear Entire Cart",
    description=(
        "**Remove all items from the user's cart at once.**\n\n"
        "Use this on the cart screen when the user taps 'Clear Cart'. "
        "After a successful subscription creation you may also clear the cart to reset state.\n\n"
        "**Note:** This endpoint must be called before `DELETE /user/cart/{cart_item_id}` "
        "in routing order to avoid path conflicts."
    )
)
def clear_cart(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return CartService.clear_cart(db, current_user["user_id"])


@router.delete(
    "/{cart_item_id}",
    response_model=RemoveFromCartResponse,
    summary="Remove a Cart Item",
    description=(
        "**Remove a single item from the cart by its `cart_item_id`.**\n\n"
        "Use `cart_item_id` from the `GET /user/cart` response. "
        "Refresh the cart after removal to update totals.\n\n"
        "**When to call:** When the user swipes or taps 'Remove' on a specific cart item."
    )
)
def remove_cart_item(
    cart_item_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return CartService.remove_cart_item(
        db,
        current_user["user_id"],
        str(cart_item_id),
    )
