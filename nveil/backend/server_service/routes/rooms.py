# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Room management routes: list, create, switch, delete, start, status."""

import asyncio
from utils import get_secret

from database.core.database import db
from database.core.dependencies import get_room_service, get_user_service
from database.models import user
from database.models.room import RoomType
from database.services.room_service import RoomService
from database.services.user_service import UserService
from database.services.license_provider import license_provider
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from logger import DEBUG, ERROR, INFO, logger
from pydantic import BaseModel
from room.room import ensure_viz, safe_stop_viz, stop_viz, stop_user_pod, _clear_room_viz_fields
from user_management.authentification import get_current_user

TEST = get_secret("TEST")
BOT_EMAIL = "bot@nveil.bob"


class StartRoomBody(BaseModel):
    room_token: str | None = None

router = APIRouter()


@router.get("/server/room/status")
async def room_status(
    room_id: str = Query(None),
    room_token: str = Cookie(None),
    current_user: user.User = Depends(get_current_user),
    room_service: RoomService = Depends(get_room_service),
):
    """Check if a room's viz instance is ready."""
    try:
        room = None
        if room_id:
            room = await room_service.room_repo.get_by_id(room_id)
        elif room_token:
            room = await room_service.room_repo.get_by_token(room_token)
        else:
            rooms = await room_service.get_user_rooms(current_user.id)
            if rooms:
                room = rooms[0]

        if not room:
            return JSONResponse({"status": "not_ready"}, status_code=404)

        if room.viz_port is not None:
            return JSONResponse({"status": "ready", "room_id": str(room.id)})
        else:
            return JSONResponse({"status": "not_ready", "room_id": str(room.id)}, status_code=404)
    except Exception as e:
        logger().logp(ERROR, f"Error checking room status: {e}")
        return JSONResponse({"status": "not_ready"}, status_code=500)


@router.get("/server/rooms/list")
async def list_rooms(
    current_user: user.User = Depends(get_current_user),
    room_service: RoomService = Depends(get_room_service),
    user_service: UserService = Depends(get_user_service),
):
    """List all chat rooms for the current user with last message preview.

    Dashboard rooms are excluded — they have their own /server/dashboards/list endpoint.
    """
    all_rooms = await room_service.get_user_rooms(current_user.id)
    rooms = [r for r in all_rooms if not hasattr(r, 'type') or r.type != RoomType.DASHBOARD]

    result = []
    for r in rooms:
        last_user_msg = None
        try:
            messages = await room_service.message_repo.get_room_messages(r.id, limit=10, offset=0)
            for msg in reversed(messages):
                if msg.author_email != BOT_EMAIL:
                    last_user_msg = msg.content
                    break
        except Exception as e:
            logger().logp(DEBUG, f"No messages for room {str(r.id)[:8]}: {e}")

        result.append({
            "id": str(r.id),
            "token": str(r.token),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "last_activity": r.last_activity.isoformat() if r.last_activity else None,
            "last_message": last_user_msg,
        })
    return result


@router.post("/server/rooms/create")
async def create_new_room(
    response: Response,
    room_token: str = Cookie(None),
    current_user: user.User = Depends(get_current_user),
    room_service: RoomService = Depends(get_room_service),
):
    """Create a new room for the current user and switch to it.

    Note: previous versions auto-deleted the empty room pointed to by the
    cookie inside this handler. That created a destructive race — concurrent
    in-flight requests (start_room, switch, WS subscribe) using the same
    cookie would 404 against a freshly-deleted token. Empty-room cleanup
    must happen out-of-band (background sweep or explicit user action), not
    inline with creation.
    """
    # Clear the previous room's viz fields if it was actively serving — pod
    # stays alive for reuse, only the DB-level association is dropped.
    if room_token:
        current_room = await room_service.room_repo.get_by_token(room_token)
        if current_room and current_room.viz_port:
            logger().logp(INFO, f"Clearing viz fields for room {str(current_room.id)[:8]} before create")
            try:
                await _clear_room_viz_fields(room_service, current_room.id)
            except Exception as e:
                await room_service.session.rollback()
                logger().logp(ERROR, f"Failed to clear viz fields: {e}")

    room = await room_service.create_room(current_user.id)
    logger().logp(INFO, f"Created new room {str(room.id)[:8]} for user {str(current_user.id)[:8]}")

    secure = TEST != "1"
    response.set_cookie(
        key="room_token", value=str(room.token), httponly=True, secure=secure, samesite="strict"
    )
    return {"id": str(room.id), "token": str(room.token)}


@router.post("/server/rooms/{room_identifier}/switch")
async def switch_room(
    room_identifier: str,
    response: Response,
    room_token: str = Cookie(None),
    current_user: user.User = Depends(get_current_user),
    room_service: RoomService = Depends(get_room_service),
):
    """Switch to a different room.

    Pod-per-user: the user's existing pod is reused via context switch.
    Clears old room's DB viz fields; ensure_viz in start_room handles pod reassignment.
    """
    target_room = await room_service.room_repo.get_by_id(room_identifier)
    if not target_room:
        target_room = await room_service.room_repo.get_by_token(room_identifier)
    if not target_room:
        raise HTTPException(status_code=404, detail="Room not found")
    membership = await room_service.room_member_repo.get_membership(target_room.id, current_user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this room")

    # Clear old room's viz fields (pod stays alive, context switches)
    if room_token:
        current_room = await room_service.room_repo.get_by_token(room_token)
        if current_room and current_room.viz_port and str(room_token) != str(target_room.token):
            logger().logp(INFO, f"Clearing viz fields for room {str(current_room.id)[:8]} before switch")
            try:
                await _clear_room_viz_fields(room_service, current_room.id)
            except Exception as e:
                await room_service.session.rollback()
                logger().logp(ERROR, f"Failed to clear viz fields on switch: {e}")

    secure = TEST != "1"
    response.set_cookie(
        key="room_token", value=str(target_room.token), httponly=True, secure=secure, samesite="strict"
    )
    logger().logp(INFO, f"User {str(current_user.id)[:8]} switched to room {str(target_room.id)[:8]}")
    return {"status": "switched", "room_id": str(target_room.id), "token": str(target_room.token)}


@router.delete("/server/rooms/{room_id}/delete")
async def delete_room(
    room_id: str,
    current_user: user.User = Depends(get_current_user),
    room_service: RoomService = Depends(get_room_service),
):
    """Delete a room. Only the owner can delete."""
    room = await room_service.room_repo.get_by_id(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if str(room.owner_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Only owner can delete room")

    if room.viz_port:
        logger().logp(INFO, f"Stopping viz for room {str(room.id)[:8]} before delete")
        asyncio.create_task(safe_stop_viz(room))

    await room_service.leave_room(room_id, current_user.id)
    logger().logp(INFO, f"Room {str(room_id)[:8]} deleted by user {str(current_user.id)[:8]}")
    return {"status": "deleted"}


@router.post("/server/room/start")
async def start_room(
    response: Response,
    body: StartRoomBody = None,
    room_token: str = Cookie(None),
    current_user: user.User = Depends(get_current_user),
):
    # Prefer explicit body token over cookie (guards against stale dashboard cookies)
    effective_token = (body.room_token if body else None) or room_token
    if not effective_token:
        raise HTTPException(status_code=400, detail="No room token")

    # Phase 1 — short DB read: room + membership
    async with db.session() as session:
        room_service = RoomService(session)
        room = await room_service.room_repo.get_by_token(effective_token)
        if not room:
            raise HTTPException(status_code=404, detail="No room found")
        if not await room_service.room_member_repo.get_membership(room.id, current_user.id):
            raise HTTPException(status_code=403, detail="User not in room")

    logger().logp(INFO, f"start_room: user={str(current_user.id)[:8]} room={str(room.id)[:8]}")
    secure = TEST != "1"

    # Phase 2 — license info + per-format feature checks
    export_features = {}
    try:
        license_info = await license_provider.get_license_info(str(current_user.id))
        if license_info and license_info.get("is_active"):
            for fmt in ("png", "jpeg", "svg", "pdf"):
                export_features[fmt] = await license_provider.check_feature(
                    str(current_user.id), fmt, "true"
                )
    except Exception as e:
        logger().logp(ERROR, f"Failed to resolve export features: {e}")

    # Phase 4 — pod allocation with no DB session held; ensure_viz opens its own short session for the write
    status = await ensure_viz(room, assign_extra={"export_features": export_features} if export_features else None)
    if status == "failed":
        raise HTTPException(status_code=500, detail="Failed to start visualization")

    content = {
        "status": "room_ready",
        "room_token": str(room.token),
    }
    resp = JSONResponse(content=content)
    resp.set_cookie(key="room_token", value=str(room.token), httponly=True, secure=secure, samesite="strict")
    return resp
