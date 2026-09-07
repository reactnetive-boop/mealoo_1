from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.schemas.user_address_schema import (
    AddUserAddressRequest,
    UpdateUserAddressRequest,
    UserAddressResponse,
    UserAddressListResponse
)
from app.services.user_address_service import UserAddressService

router = APIRouter()


@router.post(
    "/address",
    summary="Add Delivery Address",
    description=(
        "**Save a new delivery address for the user.**\n\n"
        "Users can have multiple addresses (Home, Work, Other). "
        "The returned `address_id` (UUID) is required when creating a subscription or placing an extra order — "
        "pass it as `address_id` in those requests.\n\n"
        "**When to call:** During onboarding or when the user adds a new address from settings.\n\n"
        "**Flow:** Add address → use `address_id` in `POST /user/subscription` or `POST /user/order/extra`"
    )
)
def add_address(
    payload: AddUserAddressRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    try:

        return UserAddressService.add_address(
            db,
            current_user["user_id"],
            payload
        )

    except Exception as e:

        raise


@router.get(
    "/address",
    response_model=UserAddressListResponse,
    summary="List My Addresses",
    description=(
        "**Fetch all delivery addresses saved by the user.**\n\n"
        "Use this to populate the address picker on the checkout / subscription screen. "
        "Each address has an `address_id` needed to create a subscription or extra order.\n\n"
        "**Requires:** Bearer token from `POST /user/login`"
    )
)
def get_address_list(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return UserAddressService.get_address_list(
        db,
        current_user["user_id"]
    )


@router.get(
    "/address/{address_id}",
    response_model=UserAddressResponse,
    summary="Get Address Detail",
    description=(
        "**Fetch a single saved address by its ID.**\n\n"
        "Use this to pre-fill the edit-address form.\n\n"
        "**Requires:** Bearer token from `POST /user/login`"
    )
)
def get_address(
    address_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return UserAddressService.get_address(
        db,
        current_user["user_id"],
        address_id
    )


@router.put(
    "/address/{address_id}",
    summary="Update Address",
    description=(
        "**Edit an existing delivery address.**\n\n"
        "Send only the fields that changed. "
        "Call `GET /user/address/{address_id}` first to get the current values for pre-filling the form.\n\n"
        "**Requires:** Bearer token from `POST /user/login`"
    )
)
def update_address(
    address_id: str,
    payload: UpdateUserAddressRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    try:

        return UserAddressService.update_address(
            db,
            current_user["user_id"],
            address_id,
            payload
        )

    except Exception as e:

        raise


@router.delete(
    "/address/{address_id}",
    summary="Delete Address",
    description=(
        "**Remove a saved delivery address.**\n\n"
        "Cannot delete an address that is currently linked to an active subscription. "
        "Refresh the address list after deletion.\n\n"
        "**Requires:** Bearer token from `POST /user/login`"
    )
)
def delete_address(
    address_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    try:

        return UserAddressService.delete_address(
            db,
            current_user["user_id"],
            address_id
        )

    except Exception as e:

        raise
