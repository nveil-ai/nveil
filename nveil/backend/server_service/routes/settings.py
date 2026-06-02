# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""User settings routes."""

from utils import get_secret

from shared.service_client import ServiceClient
from database.core.dependencies import get_user_service
from database.models import user
from database.services.user_service import UserService
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from logger import ERROR, logger
from user_management.authentification import get_current_user

AI_PORT = 8100
AI_HOST = get_secret("AI_HOST")

_ai_client = ServiceClient(verify=True)

router = APIRouter()


@router.get("/server/user/settings")
async def get_user_settings(
    current_user: user.User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if current_user.is_guest:
        return JSONResponse(content={"status": "success", "settings": {}, "is_guest": True})

    user_settings = await user_service.get_user_settings(current_user.id)
    try:
        host = AI_HOST or "localhost"
        resp = await _ai_client.get(
            f"https://{host}:{AI_PORT}/ai/user/settings",
            params={"user_id": str(current_user.id)},
            timeout=10.0,
        )
        if resp.ok and isinstance(resp.data, dict) and resp.data.get("status") == "success":
            user_settings.update(resp.data.get("settings", {}))
    except Exception as e:
        logger().logp(ERROR, f"Unable to retrieve AI user settings: {str(e)}")

    return JSONResponse(content={"status": "success", "settings": user_settings})


@router.post("/server/user/settings")
async def update_user_settings(
    settings: dict,
    current_user: user.User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
):
    success = True
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if current_user.is_guest:
        raise HTTPException(status_code=403, detail="Guest users cannot change settings. Please sign up to unlock this feature.")

    try:
        success = success and await user_service.update_user_settings(current_user.id, settings)
    except Exception as e:
        success = False
        logger().logp(ERROR, f"Unable to update user settings: {str(e)}")
    try:
        host = AI_HOST or "localhost"
        resp = await _ai_client.post(
            f"https://{host}:{AI_PORT}/ai/user/settings",
            json={"user_id": str(current_user.id), "settings": settings},
            timeout=10.0,
        )
        success = success and resp.ok
        if resp.ok and isinstance(resp.data, dict) and resp.data.get("status") != "success":
            logger().logp(ERROR, f"AI service failed to update user settings: {resp.data.get('message')}")
    except Exception as e:
        success = False
        logger().logp(ERROR, f"Unable to update AI user settings: {str(e)}")

    return success
