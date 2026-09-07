from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
from jose import jwt

from app.core.config import (
    JWT_SECRET_KEY,
    JWT_ALGORITHM
)

security = HTTPBearer()


def get_current_user(
    credentials = Depends(security)
):

    token = credentials.credentials

    try:

        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM]
        )

        return payload

    except Exception:

        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )


def get_current_provider(
    credentials = Depends(security)
):

    token = credentials.credentials

    try:

        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM]
        )

        return payload

    except Exception:

        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )


def get_current_admin(
    credentials = Depends(security)
):

    token = credentials.credentials

    try:

        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM]
        )

        if "admin_id" not in payload:
            raise HTTPException(
                status_code=403,
                detail="Not an admin token"
            )

        return payload

    except HTTPException:
        raise

    except Exception:

        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )


def require_super_admin(
    current=Depends(get_current_admin)
):

    if current.get("role") != "super_admin":
        raise HTTPException(
            status_code=403,
            detail="super_admin role required"
        )

    return current


def get_current_delivery_boy(
    credentials = Depends(security)
):

    token = credentials.credentials

    try:

        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM]
        )

        if "delivery_boy_id" not in payload:
            raise HTTPException(
                status_code=403,
                detail="Not a delivery boy token"
            )

        return payload

    except HTTPException:
        raise

    except Exception:

        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )