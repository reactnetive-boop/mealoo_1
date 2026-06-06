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


@router.post("/address")
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
    response_model=UserAddressListResponse
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
    response_model=UserAddressResponse
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


@router.put("/address/{address_id}")
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


@router.delete("/address/{address_id}")
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
