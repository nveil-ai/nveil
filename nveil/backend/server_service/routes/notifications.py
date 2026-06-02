# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Notification routes: stage updates, viz notifications, port registration, pod exit."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from logger import DEBUG, ERROR, INFO, SUCCESS, WARNING, logger

from database.core.dependencies import get_room_service, get_token_service, get_user_service
from database.services.room_service import RoomService
from database.services.token_service import TokenService
from database.services.user_service import UserService
from room.room import stop_viz, stop_user_pod, mark_pod_available, reload_pool, _clear_room_viz_fields
from user_management.authentification import cleanup_guest_session
from websocket_manager import ws_manager

router = APIRouter()


@router.post("/server/pool/reload")
async def pool_reload():
    """Kill all viz containers, refill the pool, and notify displaced users.

    Local dev only — allows fast viz image reload without restarting
    server/ai services. Displaced users see the idle UI and can resume
    normally (startRoom → ensure_viz → fresh pod).
    """
    count = await reload_pool()
    return {"status": "ok", "displaced_sessions": count}


@router.post("/server/stage")
async def receive_stage(data: dict):
    """Receive processing stage updates and notify web clients."""
    room_token = data.get("room_token")
    stage = data.get("stage")
    label = data.get("label")
    if not (room_token and stage and label):
        raise HTTPException(status_code=400, detail="Missing room_token, stage or label")
    await ws_manager.send(
        room_token,
        {"event": "processing_stage", "stage": stage, "label": label},
    )
    return {"status": "ok"}


@router.post("/viz/notify")
async def trame_notify(request: Request, room_service: RoomService = Depends(get_room_service)):
    """Handle incoming notifications from Trame viz service."""
    data = await request.json()
    body_room_token = data.get("room_token")
    if not body_room_token:
        raise HTTPException(status_code=400, detail="Missing room_token cookie.")
    room = await room_service.room_repo.get_by_token(body_room_token)
    if not room:
        raise HTTPException(status_code=404, detail="No room found.")
    await ws_manager.send(body_room_token, data)
    return JSONResponse({"status": "ok"})


@router.post("/server/port_ready")
async def pool_pod_ready(data: dict):
    """Called by viz pods on boot to register as available in pool."""
    pool_id = data.get("pool_id")
    if not pool_id:
        raise HTTPException(status_code=400, detail="pool_id required")
    mark_pod_available(pool_id)
    logger().logp(SUCCESS, f"Pool pod {pool_id} is now available")
    return {"status": "pool_pod_available", "pool_id": pool_id}


@router.post("/server/viz_initialized")
async def viz_initialized(data: dict):
    """Called by viz pod after Choregraph + Kedro Viz are fully ready.

    Broadcasts viz_ready WS event so the frontend knows the room is
    fully operational (iframe, Kedro Viz, etc.).
    """
    room_token = data.get("room_token")
    if not room_token:
        raise HTTPException(status_code=400, detail="room_token required")
    await ws_manager.send(room_token, {
        "event": "viz_ready",
        "room_token": room_token,
    })
    return {"status": "ok"}



@router.post("/server/handle_pod_exit")
async def handle_pod_exit(
    data: dict,
    room_service: RoomService = Depends(get_room_service),
    user_service: UserService = Depends(get_user_service),
    token_service: TokenService = Depends(get_token_service),
):
    """Handle viz pod exit (Trame server_exited lifecycle).

    Cleans up DB fields and handles guest session cleanup if applicable.
    """
    logger().logp(DEBUG, f"Pod exit notification: {data}")
    room_token = data.get("room_token")
    pool_id = data.get("pool_id")

    if not room_token and not pool_id:
        raise HTTPException(status_code=400, detail="room_token or pool_id required")
    room = None
    if room_token:
        room = await room_service.room_repo.get_by_token(room_token)
    elif pool_id:
        host = f"viz-pool-{pool_id}.viz-service.svc.cluster.local"
        room = await room_service.room_repo.get_by_hostname(host)
    if room:
        if await cleanup_guest_session(room_token, user_service, room_service, token_service):
            return {"status": "ok"}
        try:
            await _clear_room_viz_fields(room_service, room.id)
            logger().logp(INFO, f"Pod exit: viz fields cleared for room {str(room.id)[:8]}")
            return {"status": "ok"}
        except Exception as e:
            await room_service.session.rollback()
            logger().logp(ERROR, f"Error clearing viz fields on pod exit: {e}")
            raise HTTPException(status_code=500, detail="Database error clearing viz fields")
    logger().logp(WARNING, f"Pod exit: no room found for token={room_token}, pool_id={pool_id}")
    return {"status": "no_room_found"}


@router.post("/server/restart-user-viz")
async def restart_user_viz(data: dict):
    """Schedule a graceful restart of a user's viz pod.

    Sends a WebSocket warning, waits for countdown, then kills the pod.
    """
    owner_id = data.get("owner_id")
    countdown = data.get("countdown", 60)
    if not owner_id:
        raise HTTPException(status_code=400, detail="owner_id required")

    # Notify user via WebSocket
    await ws_manager.send_to_user(owner_id, {
        "event": "pod_restart_scheduled",
        "countdown": countdown,
    })
    logger().logp(INFO, f"Pod restart scheduled for owner {owner_id[:8]} in {countdown}s")

    # Schedule the actual restart
    async def _delayed_restart():
        await asyncio.sleep(countdown)
        await stop_user_pod(owner_id)
        await ws_manager.send_to_user(owner_id, {"event": "pod_restarted"})
        logger().logp(INFO, f"Pod restarted for owner {owner_id[:8]}")

    asyncio.create_task(_delayed_restart())
    return {"status": "scheduled", "countdown": countdown}
