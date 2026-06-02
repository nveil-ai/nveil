# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Unified room interface — single entry point for viz lifecycle management.

Dispatches to Docker pool (local dev) or K8s pool (staging/production)
based on the ENV environment variable.

Pod-per-user model: pods are assigned to users (not rooms). On room switch,
the existing pod is reused via context switching. Pods are only killed on
user logout, guest cleanup, or idle timeout.
"""

import asyncio
from typing import TYPE_CHECKING

from utils import get_secret

from database.models.room import Room
from logger import ERROR, INFO, SUCCESS, WARNING, logger

if TYPE_CHECKING:
    from database.services.room_service import RoomService

ENV = get_secret("ENV", "local")


def _is_local() -> bool:
    return ENV == "local"


def _get_pool():
    """Return the appropriate pool manager for the current environment."""
    if _is_local():
        from .docker_pool_manager import get_docker_pool
        return get_docker_pool()
    else:
        from .pool_manager import get_pool
        return get_pool()


# ─── Pool lifecycle ─────────────────────────────────────────────────

def start_pool() -> None:
    pool = _get_pool()
    pool._on_room_idle_callback = _handle_room_idle
    pool._on_user_idle_callback = _handle_user_idle
    if hasattr(pool, '_on_queue_wait_callback'):
        pool._on_queue_wait_callback = _handle_queue_wait
    pool.start()
    env_label = "Docker" if _is_local() else "K8s"
    logger().logp(INFO, f"{env_label} viz pool started")


# ─── Centralized DB helpers ─────────────────────────────────────────

async def _update_room_viz_fields(room_service, room_id, dns):
    """Single place where viz fields are written to DB."""
    await room_service.room_repo.update_by_id(room_id, host=dns, cmd_port=1024, viz_port=1025)
    await room_service.session.commit()


async def _clear_room_viz_fields(room_service, room_id):
    """Single place where viz fields are cleared in DB."""
    await room_service.room_repo.update_by_id(room_id, host=None, cmd_port=None, viz_port=None)
    await room_service.session.commit()


# ─── Idle callbacks (called by pool managers) ────────────────────────

async def _handle_room_idle(room_id: str):
    """Called by pool when a room times out. Clears DB + notifies frontend."""
    from database.core.database import db
    from database.services.room_service import RoomService
    from websocket_manager import ws_manager

    try:
        async with db.session() as session:
            room_service = RoomService(session)
            room = await room_service.room_repo.get_by_id(room_id)
            if room:
                await _clear_room_viz_fields(room_service, room.id)
                await ws_manager.send(str(room.token), {
                    "event": "room_idle",
                    "room_token": str(room.token),
                })
                logger().logp(INFO, f"Room {room_id[:8]} marked idle (pool callback)")
    except Exception as e:
        logger().logp(ERROR, f"Error in _handle_room_idle: {e}")


async def _handle_user_idle(owner_id: str):
    """Called by pool when a user's pod has been roomless too long."""
    from database.core.database import db
    from database.services.room_service import RoomService

    try:
        async with db.session() as session:
            room_service = RoomService(session)

            # Find rooms owned by this user that have viz fields set and clear them
            rooms = await room_service.get_user_rooms(owner_id)
            for room in rooms:
                if room.viz_port is not None:
                    await _clear_room_viz_fields(room_service, room.id)

            logger().logp(INFO, f"User {owner_id[:8]} idle cleanup done (pool callback)")
    except Exception as e:
        logger().logp(ERROR, f"Error in _handle_user_idle: {e}")


async def _handle_queue_wait(room_id: str, owner_id: str):
    """Called by pool when a user must wait for a pod. Sends viz_queued WS event."""
    from database.core.database import db
    from database.services.room_service import RoomService
    from websocket_manager import ws_manager

    try:
        async with db.session() as session:
            room_service = RoomService(session)
            room = await room_service.room_repo.get_by_id(room_id)
            if room:
                await ws_manager.send(str(room.token), {
                    "event": "viz_queued",
                    "room_token": str(room.token),
                })
                logger().logp(INFO, f"viz_queued sent for room {room_id[:8]}")
    except Exception as e:
        logger().logp(WARNING, f"Error in _handle_queue_wait: {e}")


def get_pool_manager():
    """Public accessor for the environment-appropriate pool manager."""
    return _get_pool()


def stop_pool() -> None:
    _get_pool().stop()


async def reload_pool() -> int:
    """Reload all viz containers and clean up displaced user sessions.

    Kills every viz container, refills the pool, then clears DB viz fields
    and sends ``room_idle`` WS events for each displaced room so frontends
    show the idle UI. Users can resume normally — ``startRoom`` will call
    ``ensure_viz`` which acquires a fresh pod from the refilled pool.

    Returns the number of displaced sessions.
    """
    from database.core.database import db
    from database.services.room_service import RoomService
    from websocket_manager import ws_manager

    pool = _get_pool()
    affected = await pool.reload_pool()

    for entry in affected:
        room_id = entry.get("room_id")
        if not room_id:
            continue
        try:
            async with db.session() as session:
                room_service = RoomService(session)
                room = await room_service.room_repo.get_by_id(room_id)
                if room and room.viz_port is not None:
                    await _clear_room_viz_fields(room_service, room_id)
                    await ws_manager.send(str(room.token), {
                        "event": "room_idle",
                        "room_token": str(room.token),
                    })
        except Exception as e:
            logger().logp(WARNING, f"Failed to clean up room {room_id[:8]} after pool reload: {e}")

    logger().logp(SUCCESS, f"Pool reload complete — {len(affected)} sessions displaced")
    return len(affected)


def mark_pod_available(pool_id: str) -> bool:
    return _get_pool().mark_pod_available(pool_id)


# ─── Per-room operations ────────────────────────────────────────────

async def safe_stop_viz(room: Room, timeout: int = 10) -> None:
    """Release room context from pod (pod stays alive)."""
    try:
        await asyncio.wait_for(stop_viz(room), timeout=timeout)
    except asyncio.TimeoutError:
        logger().logp(WARNING, f"stop_viz timed out for room {str(room.id)[:8]}")
    except Exception as e:
        logger().logp(WARNING, f"stop_viz failed for room {str(room.id)[:8]}: {e}")


async def stop_viz(room: Room) -> None:
    """Release room context from its pod. Pod stays alive (user-assigned, idle)."""
    room_id = str(room.id)
    logger().logp(INFO, f"stop_viz: room_id={room_id[:8]}")
    pool = _get_pool()
    await pool.release(room_id)
    logger().logp(SUCCESS, f"Room context released for room {room_id[:8]} (pod stays alive)")


async def stop_user_pod(owner_id: str) -> None:
    """Kill the pod assigned to a user. Used for logout, guest cleanup, restart."""
    logger().logp(INFO, f"stop_user_pod: owner_id={owner_id[:8]}")
    pool = _get_pool()
    await pool.release_user(owner_id)
    logger().logp(SUCCESS, f"User pod killed for owner {owner_id[:8]}")


async def ensure_viz(room: Room, assign_extra: dict = None) -> str:
    """Ensure a viz pod is serving this room.

    Returns "ready" | "failed".

    Pod-per-user model:
    - acquire() handles both cases:
      - User has pod serving different room → context switch via /viz/assign
      - User has no pod → grab one from pool, then /viz/assign

    /viz/assign is now synchronous — it blocks until the pod is ready.
    No more "starting" state; when we return "ready", the pod IS ready.

    Self-manages a short DB session for the single viz-fields write — callers
    must NOT hold a DB session across this call.
    """
    from database.core.database import db
    from database.services.room_service import RoomService

    room_id = str(room.id)
    owner_id = str(room.owner_id)
    pool = _get_pool()

    # acquire() returns: "already_serving" | "switched" | "assigned" | None
    logger().logp(INFO, f"Acquiring viz for room {room_id[:8]} (user pod reuse enabled)")
    result = await pool.acquire(room_id, str(room.token), owner_id, assign_extra=assign_extra)
    if result is None:
        logger().logp(ERROR, f"Failed to acquire viz for room {room_id[:8]}")
        return "failed"

    # Sync DB from pool
    user_pod = pool.get_user_pod_info(owner_id)
    if user_pod and user_pod.get("dns"):
        async with db.session() as session:
            await _update_room_viz_fields(RoomService(session), room.id, user_pod["dns"])

    logger().logp(SUCCESS, f"Viz ready for room {room_id[:8]} (result={result})")
    return "ready"
