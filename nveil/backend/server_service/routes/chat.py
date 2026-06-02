# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Chat routes: send user message (async), message history."""

import asyncio
import json
import time
import traceback
from typing import Optional

from database.core.database import db
from database.core.dependencies import get_room_service, get_user_service
from database.models import user
from database.services.room_service import RoomService
from database.services.user_service import UserService
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request
from logger import DEBUG, ERROR, INFO, WARNING, logger
from pydantic import BaseModel
from shared.service_client import ServiceClient
from utils import get_secret
from user_management.authentification import get_current_user
from websocket_manager import ws_manager

from shared.workspace import workspace_path as _workspace_path

AI_PORT = 8100
AI_HOST = get_secret("AI_HOST")

router = APIRouter()


async def _send_bot_message(room_service, user_service, room_id, room_token, text, suggestions=None, selection_prompt=None):
    """Unified: save bot message to DB + push chat_response via WS."""
    if suggestions is None:
        suggestions = []
    bot = await user_service.user_repo.get_by_email("bot@nveil.bob")
    if not bot:
        bot = await user_service.create_user("bot", "bot@nveil.bob", "")
        await room_service.session.commit()
    if text:
        await room_service.send_message(room_id, bot.id, text)
        await room_service.session.commit()
    payload = {
        "event": "chat_response",
        "text": text,
        "suggestions": suggestions,
    }
    if selection_prompt:
        payload["selection_prompt"] = selection_prompt
    await ws_manager.send(room_token, payload)

# Track background tasks to prevent garbage collection
_background_tasks = []

# AI service client with circuit breaker — fast-fails after 3 consecutive failures
_ai_client = ServiceClient(
    max_retries=0,
    circuit_threshold=3,
    circuit_recovery=30.0,
)


async def _process_chat_background(
    input_data: dict,
    cookies: dict,
    room_id: str,
    room_token: str,
    user_id: str,
    start_time: float,
):
    """Background task: call AI service, save response, push via WebSocket."""
    async with db.session() as session:
        room_service_bg = RoomService(session)
        user_service_bg = UserService(session)

        try:
            host = AI_HOST or "localhost"
            url = f"https://{host}:{AI_PORT}/ai/process_user_message"
            resp = await _ai_client.post(
                url, json=input_data, cookies=cookies, timeout=300.0
            )

            if not resp.ok:
                error_code = resp.error_code or ""
                if error_code == "CIRCUIT_OPEN":
                    logger().logp(ERROR, f"AI service circuit breaker open — fast-failing")
                    await _save_and_notify_error(
                        session, room_service_bg, user_service_bg, room_id, room_token,
                        "<i>Something went wrong. Please try again in a moment.</i>",
                    )
                    return
                logger().logp(ERROR, f"AI service error: {resp.error}")
                await _save_and_notify_error(
                    session, room_service_bg, user_service_bg, room_id, room_token,
                    "<i>Something went wrong while processing your request. Please try again shortly.</i>",
                )
                return

            ai_response = resp.data

            total_duration = time.perf_counter() - start_time
            logger().logp(INFO, f"⏱️  Request processed in {total_duration:.2f} seconds (backend side).")

            await _send_bot_message(
                room_service_bg, user_service_bg, room_id, room_token,
                ai_response.get("text", ""), ai_response.get("suggestions", []),
                selection_prompt=ai_response.get("selection_prompt"),
            )

        except Exception as e:
            logger().logp(ERROR, f"❌ Background chat error: {str(e)}")
            logger().logp(ERROR, traceback.format_exc())
            await _save_and_notify_error(
                session, room_service_bg, user_service_bg, room_id, room_token,
                "<i>Something went wrong. Please try again in a few seconds or refresh the page.</i>",
            )


async def _save_and_notify_error(session, room_service_bg, user_service_bg, room_id, room_token, error_text):
    """Save error message as bot response and notify via WebSocket."""
    try:
        await _send_bot_message(room_service_bg, user_service_bg, room_id, room_token, error_text)
    except Exception as save_err:
        logger().logp(ERROR, f"Failed to save error message: {save_err}")


@router.post("/ai/sendUserMessage")
async def chat_endpoint(
    request: Request,
    room_token: str = Cookie(None),
    current_user: user.User = Depends(get_current_user),
    room_service: RoomService = Depends(get_room_service),
    user_service: UserService = Depends(get_user_service),
):
    """Async chat endpoint. Returns immediately; pushes result via WebSocket."""
    # Block chat for guest users entirely
    if current_user.is_guest:
        raise HTTPException(status_code=403, detail="Chat is disabled for guest users")

    start_time = time.perf_counter()
    try:
        body = await request.body()
        data = json.loads(body.decode())
        isUpload = False
        if "messages" in data:
            messages = data["messages"]
            if not messages:
                raise HTTPException(status_code=400, detail="No messages provided")
            last_message = messages[-1]
            if not last_message:
                return {"error": "No message received"}
            text = last_message.get("text")
            if not text:
                raise HTTPException(status_code=400, detail="No text in message")
        elif "text" in data:
            text = data["text"]
        else:
            raise HTTPException(status_code=400, detail="Invalid request format")
        isSelection = False
        if "custom" in data["messages"][-1]:
            custom = data["messages"][-1]["custom"]
            if "upload" in custom:
                isUpload = custom["upload"]
            if "selection" in custom:
                isSelection = bool(custom["selection"])
        room = await room_service.room_repo.get_by_token(room_token)

        logger().logp(DEBUG, f"message on the way: {text}")
        await room_service.send_message(room.id, current_user.id, text)

        try:
            message_history = await room_service.get_room_messages(room.id, current_user.id, 100)
        except Exception as e:
            logger().logp(WARNING, f"Could not fetch message history for AI payload: {e}")
            message_history = []

        input_data = {
            "message": text,
            "is_upload": isUpload,
            "is_selection": isSelection,
            "xml_path": str(_workspace_path(str(room.owner_id), str(room.id))),
            "room_token": room_token,
            "room_id": str(room.id),
            "owner_id": str(room.owner_id),
            "user_id": str(current_user.id),
            "message_history": [m.model_dump(mode="json") for m in message_history],
            "user_language": data.get("user_language", "en"),
        }

        await room_service.session.commit()

        task = asyncio.create_task(
            _process_chat_background(
                input_data=input_data,
                cookies=dict(request.cookies),
                room_id=str(room.id),
                room_token=room_token,
                user_id=str(current_user.id),
                start_time=start_time,
            )
        )
        _background_tasks.append(task)
        task.add_done_callback(lambda t: _background_tasks.remove(t) if t in _background_tasks else None)

        return {"text": "", "async": True}

    except Exception as e:
        logger().logp(ERROR, f"❌ Error: {str(e)}")
        logger().logp(ERROR, traceback.format_exc())
        return {
            "text": "<i>The visualization generation stopped prematurely. Please retry again in a few seconds or refresh the page.</i>"
        }


class ChatHistoryRequest(BaseModel):
    nb: Optional[int] = 40
    room_id: Optional[str] = None
    room_token: Optional[str] = None
    offset: Optional[int] = 0


@router.post("/server/chat/messages")
async def send_message_history(
    request: ChatHistoryRequest,
    room_id_cookie: str = Cookie(None, alias="room_id"),
    room_token_cookie: str = Cookie(None, alias="room_token"),
    current_user: user.User = Depends(get_current_user),
    room_service: RoomService = Depends(get_room_service),
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Guests get static chat history from chat.json (no DB query)
    if current_user.is_guest:
        from user_management.guest_utils import get_guest_chat_history
        raw = get_guest_chat_history()
        actual_token = room_token_cookie or ""
        return [
            {
                "id": str(i),
                "content": msg.get("text", "").replace("GUEST_ROOM_TOKEN", actual_token),
                "author_email": "bot@nveil.bob" if msg.get("role") == "bot" else "guest@temp.nveil.local",
                "room_token": "",
                "created_at": msg.get("created_at"),
            }
            for i, msg in enumerate(raw)
        ]

    room = None
    if request.room_id:
        room = await room_service.room_repo.get_by_id(request.room_id)
    elif request.room_token:
        room = await room_service.room_repo.get_by_token(request.room_token)
    elif room_token_cookie:
        room = await room_service.room_repo.get_by_token(room_token_cookie)
    elif room_id_cookie:
        room = await room_service.room_repo.get_by_id(room_id_cookie)

    if not room:
        user_rooms = await room_service.get_user_rooms(current_user.id)
        if not user_rooms:
            raise HTTPException(status_code=404, detail="No room found for user")
        room = user_rooms[0]

    try:
        messages = await room_service.get_room_messages(room.id, current_user.id, request.nb, request.offset)
        return messages
    except Exception as e:
        logger().logp(ERROR, e)
        return []


@router.get("/server/get_history")
async def get_room_messages(
    room_id: str = Query(None),
    room_token: str = Query(None),
    nb: int | None = Query(None),
    current_user: user.User = Depends(get_current_user),
    room_service: RoomService = Depends(get_room_service),
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Guests get static chat history
    if current_user.is_guest:
        from user_management.guest_utils import get_guest_chat_history
        raw = get_guest_chat_history()
        actual_token = room_token or ""
        return [
            {
                "id": str(i),
                "content": msg.get("text", "").replace("GUEST_ROOM_TOKEN", actual_token),
                "author_email": "bot@nveil.bob" if msg.get("role") == "bot" else "guest@temp.nveil.local",
                "room_token": "",
                "created_at": msg.get("created_at"),
            }
            for i, msg in enumerate(raw)
        ]

    room = None
    if room_id:
        room = await room_service.room_repo.get_by_id(room_id)
    elif room_token:
        room = await room_service.room_repo.get_by_token(room_token)

    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    messages = await room_service.get_room_messages(room.id, current_user.id, nb)
    return messages


@router.post("/server/bot_message")
async def bot_message(
    data: dict,
    room_service: RoomService = Depends(get_room_service),
    user_service: UserService = Depends(get_user_service),
):
    """Endpoint for AI background tasks to send bot messages (Phase 2 follow-ups)."""
    room_token = data.get("room_token")
    if not room_token:
        raise HTTPException(status_code=400, detail="Missing room_token")
    room = await room_service.room_repo.get_by_token(room_token)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    await _send_bot_message(
        room_service, user_service, str(room.id), room_token,
        data.get("text", ""), data.get("suggestions", []),
    )
    return {"status": "ok"}
