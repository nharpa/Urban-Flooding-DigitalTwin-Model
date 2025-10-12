"""Authentication utilities for Urban Flooding Digital Twin API.

This module provides token-based authentication for the FastAPI endpoints.
It implements Bearer token authentication with configurable API keys for
securing access to the digital twin services.
"""

from __future__ import annotations

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from digital_twin.auth.config import settings

security = HTTPBearer()


def get_api_token() -> str:
    """Retrieve the configured API token from settings.

    Returns
    -------
    str
        The API token configured in environment variables.

    Raises
    ------
    ValueError
        If API_TOKEN is not configured or is empty.
    """
    token = settings.API_TOKEN
    if not token:
        raise ValueError("API_TOKEN is not configured")
    return token


def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    """Verify the provided Bearer token against the configured API token.

    Parameters
    ----------
    credentials : HTTPAuthorizationCredentials
        Bearer token credentials from the HTTP Authorization header.

    Returns
    -------
    str
        The verified token if authentication succeeds.

    Raises
    ------
    HTTPException
        If the token is invalid or missing (HTTP 403 Forbidden).
    """
    token = credentials.credentials
    api_token = get_api_token()

    if token != api_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token
