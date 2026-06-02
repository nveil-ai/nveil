# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""API key authentication dependencies for the public API."""

from typing import List, Tuple

from fastapi import Depends, Header, HTTPException, Request, status

from database.core.dependencies import get_db
from database.models.api_key import ApiKey
from database.models.user import User
from database.services.api_key_service import ApiKeyService
from sqlalchemy.ext.asyncio import AsyncSession


def get_api_key_service(session: AsyncSession = Depends(get_db)) -> ApiKeyService:
    return ApiKeyService(session)


async def get_api_user(
    request: Request,
    x_api_key: str = Header(None, alias="X-API-Key"),
    api_key_service: ApiKeyService = Depends(get_api_key_service),
) -> Tuple[User, ApiKey]:
    """Authenticate a request via API key.

    Accepts the key from:
    - ``X-API-Key`` header
    - ``Authorization: Bearer nveil_...`` header
    """
    raw_key = x_api_key

    if not raw_key:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer nveil_"):
            raw_key = auth_header.split(" ", 1)[1]

    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Pass via X-API-Key header or Authorization: Bearer nveil_...",
        )

    result = await api_key_service.validate_key(raw_key)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or revoked API key",
        )

    return result


def require_scope(*required_scopes: str):
    """Dependency factory that checks the API key has the required scopes."""

    async def _check(
        auth: Tuple[User, ApiKey] = Depends(get_api_user),
        api_key_service: ApiKeyService = Depends(get_api_key_service),
    ) -> Tuple[User, ApiKey]:
        user, api_key = auth
        key_scopes = api_key_service.get_scopes(api_key)
        missing = [s for s in required_scopes if s not in key_scopes]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key missing required scope(s): {', '.join(missing)}",
            )
        return user, api_key

    return _check
