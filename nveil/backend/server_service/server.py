# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import os
import re
import sys
from contextlib import asynccontextmanager
from typing import Optional
from uuid import uuid4

import httpx
from fastapi import (Cookie, FastAPI, HTTPException, Query, Request,
                     WebSocket, WebSocketDisconnect)
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from logger import DEBUG, ERROR, INFO, WARNING, logger
from middleware.security_headers import SecurityHeadersMiddleware
from shared.security import sanitize_file_path
from sqlalchemy import text
from sqlalchemy.schema import CreateSchema
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware

from utils import get_secret

logger(service="SERVER", service_id="MAIN")

httpx_client: httpx.AsyncClient = None

backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

DATABASE_URL = get_secret("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Set the env var or add it in backend/.env"
    )

from database.core.database import db
from database.services.room_service import RoomService
from room.room import start_pool, stop_pool
from websocket_manager import ws_manager

DB_SCHEMA = get_secret("DATABASE_SCHEMA")
AI_PORT = 8100
AI_HOST = get_secret("AI_HOST")

# Cache-Control for the SPA HTML shell. max-age=60 keeps browsers fresh after
# deploys (CI purges Cloudflare anyway); s-maxage=604800 lets Cloudflare's
# edge hold it for a week; stale-while-revalidate=2592000 lets the edge serve
# stale for 30 more days while it refetches in background.
SPA_CACHE_HEADERS = {
    "Cache-Control": "public, max-age=60, s-maxage=604800, stale-while-revalidate=2592000"
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    try:
        db.initialize(url=DATABASE_URL, echo=False)
        from database.models.base import Base
        async with db.engine.begin() as conn:
            await conn.execute(CreateSchema(DB_SCHEMA, if_not_exists=True))
            await conn.run_sync(Base.metadata.create_all)
        logger().logp(INFO, "✅ Database tables initialized")

        # Clear stale viz fields — all containers are killed on restart,
        # so any DB entries with host/port set are guaranteed stale.
        from sqlalchemy import update as sa_update
        from database.models.room import Room
        async with db.engine.begin() as conn:
            result = await conn.execute(
                sa_update(Room).where(Room.host.isnot(None)).values(
                    host=None, cmd_port=None, viz_port=None
                )
            )
            if result.rowcount:
                logger().logp(INFO, f"Cleared stale viz fields from {result.rowcount} rooms")
    except Exception as e:
        logger().logp(ERROR, f"❌ Database initialization failed: {e}")
        raise

    # Provision shared guest workspace template + seed shared dashboard
    try:
        from user_management.guest_utils import ensure_guest_dashboard
        async with db.session() as seed_session:
            await ensure_guest_dashboard(seed_session)
        logger().logp(INFO, "Guest infrastructure provisioned")
    except Exception as e:
        logger().logp(ERROR, f"Failed to provision guest infrastructure: {e}")

    start_pool()
    global httpx_client
    limits = httpx.Limits(max_connections=200, max_keepalive_connections=20)
    httpx_client = httpx.AsyncClient(limits=limits, http2=True, verify=True)

    # Share httpx client with viz_proxy module
    from routes.viz_proxy import set_httpx_client
    set_httpx_client(httpx_client)

    yield

    # SHUTDOWN
    stop_pool()
    logger().logp(INFO, "Shutdown ...!!!")
    if httpx_client:
        await httpx_client.aclose()
    await db.close()


# ── Create the app via factory, with production lifespan ──────────────
from app_factory import create_app

app = create_app(lifespan=lifespan)

frontend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")

# ── Static files ──────────────────────────────────────────────────────

_assets_dir = os.path.join(frontend_dir, "assets")
_icons_dir = os.path.join(frontend_dir, "icons")

os.makedirs(_assets_dir, exist_ok=True)
app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

os.makedirs(_icons_dir, exist_ok=True)
app.mount("/icons", StaticFiles(directory=_icons_dir), name="icons")


# ── WebSocket for frontend events ────────────────────────────────────

@app.websocket("/ws/events")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(None),
    room_token: str = Cookie(None),
):
    """Session-level WebSocket endpoint.

    Accepts connections without requiring a room token upfront.
    Clients send {"action": "subscribe", "room_token": "..."} to subscribe to room events.
    Backward compatible: if ?token= query param is provided, auto-subscribes to that room.
    """
    conn_id = str(uuid4())
    logger().logp(DEBUG, f"🔍 Incoming WebSocket request on /ws/events [conn_id: {conn_id[:8]}...] (Query token: {token}, Cookie token: {room_token})")

    await websocket.accept()
    ws_manager.connect(conn_id, websocket)

    # Backward compatibility: auto-subscribe if token provided via query or cookie
    effective_token = token or room_token
    if effective_token:
        async with db.session() as session:
            room = await RoomService(session).room_repo.get_by_token(effective_token)
        if room:
            ws_manager.subscribe(conn_id, effective_token)
            last = ws_manager.get_last_event(effective_token)
            if last:
                await websocket.send_json(last)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue

            if data.get("action") == "subscribe":
                new_room_token = data.get("room_token")
                if new_room_token:
                    async with db.session() as session:
                        room = await RoomService(session).room_repo.get_by_token(new_room_token)
                    if room:
                        ws_manager.subscribe(conn_id, new_room_token)
                        last = ws_manager.get_last_event(new_room_token)
                        if last:
                            await websocket.send_json(last)
                    else:
                        logger().logp(WARNING, f"⚠️ Subscribe rejected: room_token={new_room_token[:8]}... not found")
    except (WebSocketDisconnect, Exception) as e:
        logger().logp(INFO, f"🔌 WebSocket disconnected [conn_id: {conn_id[:8]}...] (Reason: {e})")
        ws_manager.disconnect(conn_id)


# ---- AI service proxies (thin forwarding) ----

@app.post("/ai/clear")
async def clear_state():
    try:
        host = AI_HOST or "localhost"
        response = await httpx_client.post(f"https://{host}:{AI_PORT}/ai/clear", timeout=10.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        return {"message": f"Failed to clear state: {str(e)}"}


@app.get("/ai/debug/state")
async def debug_state():
    try:
        host = AI_HOST or "localhost"
        response = await httpx_client.get(f"https://{host}:{AI_PORT}/ai/debug/state", timeout=10.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        return {"state_info": f"Could not retrieve state info: {str(e)}"}


@app.get("/ai/health")
async def ai_health_check():
    try:
        host = AI_HOST or "localhost"
        response = await httpx_client.get(f"https://{host}:{AI_PORT}/ai/health", timeout=10.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        return {"status": "error", "message": f"AI service is unreachable: {str(e)}"}


# ---- SPA Routing & 404 Handling ----

VALID_SPA_ROUTES = [
    r"^/?$",
    r"^/settings/?$",
    r"^/explore/?$",
    r"^/data/?$",
    r"^/feedback/?$",
    r"^/plan/?$",
    r"^/success/?$",
    r"^/cancel/?$",
    r"^/error/?$",
    r"^/404/?$",
    r"^/room/[^/]+/?$",
    r"^/dashboards/?$",
    r"^/dashboard/[^/]+/?$",
]

# ---- Frontend serving ----

from server_service.bot_detection import is_bot


def get_snapshot_response(request: Request, path: str = "") -> Optional[FileResponse]:
    user_agent = request.headers.get("user-agent", "")
    cf_client_bot = request.headers.get("x-is-bot", "")
    if is_bot(user_agent, cf_client_bot):
        if path:
            snapshot_path = os.path.join(frontend_dir, "snapshots", path, "index.html")
        else:
            snapshot_path = os.path.join(frontend_dir, "snapshots", "index.html")

        # Sanitize the snapshot path to prevent directory traversal
        try:
            sanitize_file_path(snapshot_path, frontend_dir)
        except ValueError as e:
            logger().logp(ERROR, f"Invalid snapshot path: {e}")
            return None

        if os.path.exists(snapshot_path) and os.path.isfile(snapshot_path):
            return FileResponse(snapshot_path)
    return None


@app.get("/")
async def serve_index(request: Request):
    # Check for index.html or index.php in path (though usually handled by higher level rules, good for consistency)
    path = request.url.path
    if path.endswith(("/index.html")):
        new_url = "/" + (f"?{request.url.query}" if request.url.query else "")
        return RedirectResponse(url=new_url, status_code=301)

    snapshot_response = get_snapshot_response(request)
    if snapshot_response:
        return snapshot_response
    return FileResponse(os.path.join(frontend_dir, "index.html"), headers=SPA_CACHE_HEADERS)


@app.get("/room/{room_id}")
async def serve_room_index(room_id: str):
    return FileResponse(os.path.join(frontend_dir, "index.html"), headers=SPA_CACHE_HEADERS)


@app.get("/room/{room_id}/{rest:path}")
async def serve_room_index_catchall(room_id: str, rest: str):
    return RedirectResponse(url=f"/room/{room_id}", status_code=307)


@app.get("/data")
async def serve_data_index():
    return FileResponse(os.path.join(frontend_dir, "index.html"), headers=SPA_CACHE_HEADERS)


@app.get("/dashboards")
async def serve_dashboards_index():
    return FileResponse(os.path.join(frontend_dir, "index.html"), headers=SPA_CACHE_HEADERS)


@app.get("/dashboard/{dashboard_token}")
async def serve_dashboard_view(dashboard_token: str):
    return FileResponse(os.path.join(frontend_dir, "index.html"), headers=SPA_CACHE_HEADERS)


@app.get("/{path:path}")
def serve_react_app(path: str, request: Request):
    # Handle direct requests for index files
    if path.endswith(("index.html")):
        new_url = "/" + (f"?{request.url.query}" if request.url.query else "")
        return RedirectResponse(url=new_url, status_code=301)

    file_path = os.path.join(frontend_dir, path)

    # Sanitize the file path to prevent directory traversal
    try:
        sanitize_file_path(file_path, frontend_dir)
    except ValueError as e:
        logger().logp(ERROR, f"Invalid file path: {e}")
        # Return index.html with 404 status for React Router to handle
        return FileResponse(os.path.join(frontend_dir, "index.html"), status_code=404, headers=SPA_CACHE_HEADERS)

    # Serve static files if they exist
    if os.path.exists(file_path) and os.path.isfile(file_path):
        headers = {}
        if path.startswith("assets/"):
            # Vite hashed assets are immutable — cache for 1 year (all file types)
            # (Note: /assets/ AND /vendor/ are both actually served by
            # PreCompressedStaticMiddleware before reaching here, with the same
            # 1-year immutable cache — this branch is a defensive fallback.)
            headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif path.startswith("Fonts/"):
            # Self-hosted fonts rarely change — cache for 30 days
            headers["Cache-Control"] = "public, max-age=2592000"
        elif path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.ico', '.webp', '.svg', '.webm', '.woff2', '.ttf')):
            headers["Cache-Control"] = "public, max-age=86400"
        return FileResponse(file_path, headers=headers)

    # Check for pre-rendered snapshots (for SEO/bots)
    snapshot_response = get_snapshot_response(request, path)
    if snapshot_response:
        return snapshot_response

    # Check if the path matches a known frontend route
    normalized_path = f"/{path.strip('/')}" if path else "/"
    is_valid_route = any(re.match(pattern, normalized_path) for pattern in VALID_SPA_ROUTES)

    # Return index.html for SPA routing - with 404 status if route is invalid
    status_code = 200 if is_valid_route else 404
    return FileResponse(os.path.join(frontend_dir, "index.html"), status_code=status_code, headers=SPA_CACHE_HEADERS)
