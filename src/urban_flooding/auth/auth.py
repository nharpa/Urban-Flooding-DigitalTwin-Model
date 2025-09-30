from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import os
from typing import Optional
from src.urban_flooding.auth.config import settings

security = HTTPBearer()


def get_api_token() -> str:
    token = settings.API_TOKEN
    if not token:
        raise ValueError("API_TOKEN is not configured")
    return token


def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    token = credentials.credentials
    api_token = get_api_token()

    if token != api_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token
