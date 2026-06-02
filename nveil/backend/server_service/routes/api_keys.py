# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""API key management routes.

These endpoints use JWT cookie auth (get_current_user) — they are management
endpoints for the web UI, not the public API itself.

Security: the plaintext key is returned **only once** at creation.
Only the SHA-512 hash is stored — the key cannot be recovered.
If lost, the user must revoke and create a new one.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from database.core.dependencies import get_db
from database.models.user import User
from database.services.api_key_service import ApiKeyService
from sqlalchemy.ext.asyncio import AsyncSession
from user_management.authentification import get_current_user

router = APIRouter()

VALID_SCOPES = [
    "visualization:generate",
]


def _get_api_key_service(session: AsyncSession = Depends(get_db)) -> ApiKeyService:
    return ApiKeyService(session)


# --- Request / Response schemas ---


class CreateKeyRequest(BaseModel):
    name: str
    scopes: List[str] = VALID_SCOPES
    expires_at: Optional[datetime] = None


# --- Endpoints ---


@router.post("/keys")
async def create_api_key(
    body: CreateKeyRequest,
    current_user: User = Depends(get_current_user),
    api_key_service: ApiKeyService = Depends(_get_api_key_service),
):
    """Create a new API key for the current user.

    The plaintext key is returned in ``key_value`` — this is the **only time**
    it will ever be shown. Store it securely.
    """
    invalid = [s for s in body.scopes if s not in VALID_SCOPES]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scope(s): {', '.join(invalid)}. Valid: {', '.join(VALID_SCOPES)}",
        )

    plaintext_key, api_key = await api_key_service.create_key(
        user_id=current_user.id,
        name=body.name,
        scopes=body.scopes,
        expires_at=body.expires_at,
    )

    return JSONResponse(
        status_code=201,
        content={
            "id": str(api_key.id),
            "name": api_key.name,
            "key_value": plaintext_key,  # shown ONCE only
            "key_prefix": api_key.key_prefix,
            "scopes": body.scopes,
            "created_at": api_key.created_at.isoformat() if api_key.created_at else None,
            "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None,
        },
    )


@router.get("/keys")
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    api_key_service: ApiKeyService = Depends(_get_api_key_service),
):
    """List all API keys for the current user.

    Returns metadata only — the key itself is never returned after creation.
    """
    keys = await api_key_service.list_keys(current_user.id)
    result = []
    for k in keys:
        result.append({
            "id": str(k.id),
            "name": k.name,
            "key_prefix": k.key_prefix,
            "scopes": api_key_service.get_scopes(k),
            "is_active": k.is_active,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "expires_at": k.expires_at.isoformat() if k.expires_at else None,
            "created_at": k.created_at.isoformat() if k.created_at else None,
            "total_requests": k.total_requests,
            "total_generations": k.total_generations,
        })
    return JSONResponse(content=result)


@router.delete("/keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    current_user: User = Depends(get_current_user),
    api_key_service: ApiKeyService = Depends(_get_api_key_service),
):
    """Revoke an API key."""
    await api_key_service.revoke_key(key_id, current_user.id)
    return JSONResponse(content={"status": "revoked"})
