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