# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Viz proxy routes: command forwarding, Trame WebSocket/HTTP proxy, Kedro Viz proxy."""

import asyncio
import mimetypes
from pathlib import Path

import httpx
from fastapi import (APIRouter, Cookie, HTTPException, Request,
                     Response, WebSocket)
from room.room import get_pool_manager as get_pool
from fastapi.responses import FileResponse
from logger import DEBUG, ERROR, INFO, WARNING, logger
from shared.security import sanitize_file_path
from starlette.requests import ClientDisconnect
from starlette.websockets import WebSocketDisconnect
try:
    from websockets.asyncio.client import connect as ws_connect  # v14+
except ImportError:
    from websockets.client import connect as ws_connect  # v11-13
from websockets.exceptions import ConnectionClosed

# Will be set from server.py after lifespan creates the client
httpx_client: httpx.AsyncClient = None

# Viz pod port constants — hardcoded in pool_manager._build_service, never per-room
_VIZ_PORT = 1025
_CMD_PORT = 1024

router = APIRouter()


def set_httpx_client(client: httpx.AsyncClient):
    """Called by server.py to share the global httpx client."""
    global httpx_client
    httpx_client = client


def _resolve_dns(room_token: str) -> str:
    """Resolve room_token to pod DNS via pool_manager in-memory routing."""
    if not room_token:
        raise HTTPException(status_code=401, detail="Missing room_token cookie")
    host = get_pool().get_pod_dns_for_token(room_token)
    if not host:
        raise HTTPException(status_code=503, detail="Viz service not ready yet.")
    return host


def _resolve_info(room_token: str) -> dict:
    """Resolve room_token to full info (dns, room_id, owner_id) via pool_manager."""
    if not room_token:
        raise HTTPException(status_code=401, detail="Missing room_token cookie")
    info = get_pool().get_room_info_for_token(room_token)
    if not info or not info.get("dns"):
        raise HTTPException(status_code=503, detail="Viz service not ready yet.")
    return info


def _resolve_info_by_room_id(room_id: str) -> dict:
    """Resolve room_id to full info (dns, room_id, owner_id) via pool_manager."""
    if not room_id:
        raise HTTPException(status_code=400, detail="room_id is required")
    info = get_pool().get_room_info_for_room_id(room_id)
    if not info or not info.get("dns"):
        raise HTTPException(status_code=503, detail="Viz service not ready yet.")
    return info


@router.post("/viz/send")
async def send_to_trame(
    data: dict,
    room_token: str = Cookie(None),
):
    """Send data to a Trame server via an HTTP POST request."""
    host = _resolve_dns(room_token)
    data_with_token = data.copy()
    data_with_token["room_token"] = room_token
    try:
        response = await httpx_client.post(
            f"https://{host}:{_CMD_PORT}/viz/handle_command",
            json=data_with_token,
            timeout=60.0,
        )
        response.raise_for_status()
        if response.content:
            return response.json()
        else:
            return {"status": "ok"}
    except httpx.HTTPStatusError as e:
        logger().logp(ERROR, f"HTTP error while sending to Trame: {e}")
        return {"status": f"HTTP error while sending to Trame: {e}"}
    except Exception as e:
        logger().logp(ERROR, f"Error while sending to Trame: {e}")
        return {"status": f"Error while sending to Trame: {e}"}


@router.post("/viz/request_loading")
async def viz_load_file(
    data: dict,
):
    """Delegate file loading to the viz service."""
    try:
        room_id = data.get("room_id")
        info = _resolve_info_by_room_id(room_id)
        host = info["dns"]
        logger().logp(DEBUG, f"Delegating file load to Viz for room_id: {room_id}")
        data["owner_id"] = info["owner_id"]
        response = await httpx_client.post(
            f"https://{host}:{_CMD_PORT}/viz/load_files", json=data, timeout=60.0
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        logger().logp(ERROR, f"HTTP error while delegating file load to Viz: {e}")
        raise HTTPException(status_code=502, detail=f"HTTP error: {e}")


@router.post("/viz/run_choregraph")
async def proxy_run_choregraph(
    data: dict,
):
    """Proxy Choregraph execution request to the Viz service."""
    try:
        room_id = data.get("room_id")
        info = _resolve_info_by_room_id(room_id)
        host = info["dns"]
        url = f"https://{host}:{_CMD_PORT}/viz/run_choregraph"
        response = await httpx_client.post(url, json=data, timeout=120.0)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger().logp(ERROR, f"Error proxying run_choregraph: {e}")
        return {"status": "error", "details": str(e)}


@router.post("/viz/refresh_url_sources")
async def proxy_refresh_url_sources(
    data: dict,
    room_token: str = Cookie(None),
):
    """Proxy URL source refresh request to the Viz service."""
    try:
        info = _resolve_info(room_token)
        host = info["dns"]
        data["room_id"] = info["room_id"]
        data["owner_id"] = info["owner_id"]
        response = await httpx_client.post(
            f"https://{host}:{_CMD_PORT}/viz/refresh_url_sources", json=data, timeout=120.0
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger().logp(ERROR, f"Error proxying refresh_url_sources: {e}")
        return {"status": "error", "details": str(e)}


@router.post("/viz/set_plot_theme")
async def proxy_set_plot_theme(
    data: dict,
    room_token: str = Cookie(None),
):
    """Proxy plot theme change to the Viz service."""
    try:
        host = _resolve_dns(room_token)
        response = await httpx_client.post(
            f"https://{host}:{_CMD_PORT}/viz/set_plot_theme", json=data, timeout=30.0
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger().logp(ERROR, f"Error proxying set_plot_theme: {e}")
        return {"status": "error", "details": str(e)}


@router.post("/viz/refresh_all")
async def proxy_refresh_all(
    room_token: str = Cookie(None),
):
    """Proxy dashboard refresh-all request to the Viz service."""
    try:
        host = _resolve_dns(room_token)
        response = await httpx_client.post(
            f"https://{host}:{_CMD_PORT}/viz/refresh_all", json={}, timeout=120.0
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger().logp(ERROR, f"Error proxying refresh_all: {e}")
        return {"status": "error", "details": str(e)}


@router.post("/viz/set_refresh_interval")
async def proxy_set_refresh_interval(
    data: dict,
    room_token: str = Cookie(None),
):
    """Proxy refresh interval configuration to the Viz service."""
    try:
        info = _resolve_info(room_token)
        host = info["dns"]
        data["room_id"] = info["room_id"]
        data["owner_id"] = info["owner_id"]
        response = await httpx_client.post(
            f"https://{host}:{_CMD_PORT}/viz/set_refresh_interval", json=data, timeout=30.0
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger().logp(ERROR, f"Error proxying set_refresh_interval: {e}")
        return {"status": "error", "details": str(e)}


# ---- WebSocket proxy for Trame ----

@router.websocket("/viz/app/ws")
async def viz_ws_proxy(
    client_ws: WebSocket,
    room_token: str = Cookie(None),
):
    logger().logp(INFO, f"🔌 [PROXY] WebSocket connection attempt on /viz/app/ws [ID: {hex(id(client_ws))}] for room_token={room_token[:8] if room_token else 'None'}...")
    if not room_token:
        await client_ws.close(code=1008)
        return
    host = get_pool().get_pod_dns_for_token(room_token)
    if not host:
        await client_ws.close(code=1008)
        return
    await client_ws.accept()
    viz_ws_url = f"ws://{host}:{_VIZ_PORT}/ws"
    max_retries = 10
    retry_delay = 0.5
    ping_interval = 20.0
    ping_timeout = 60.0
    attempt = 0
    while True:
        try:
            async with ws_connect(viz_ws_url, max_size=None, ping_interval=ping_interval, ping_timeout=ping_timeout) as server_ws:
                async def forward(ws_from, ws_to):
                    try:
                        while True:
                            data = await (
                                ws_from.receive() if ws_from == client_ws else ws_from.recv()
                            )
                            if ws_to == server_ws:
                                message_content = data.get("bytes") or data.get("text")
                                if message_content:
                                    await server_ws.send(message_content)
                            else:
                                if isinstance(data, str):
                                    await client_ws.send_text(data)
                                elif isinstance(data, bytes):
                                    await client_ws.send_bytes(data)
                    except (WebSocketDisconnect, ConnectionClosed) as e:
                        logger().logp(DEBUG, f"WebSocket forwarder disconnected: {e}")
                    except Exception as e:
                        logger().logp(INFO, f"WebSocket forwarder closing with error: {e}")

                client_to_server_task = asyncio.create_task(forward(client_ws, server_ws))
                server_to_client_task = asyncio.create_task(forward(server_ws, client_ws))
                done, pending = await asyncio.wait(
                    [client_to_server_task, server_to_client_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                logger().logp(INFO, f"🔌 [PROXY] Lost WS connection [ID: {hex(id(client_ws))}]")
                for task in done:
                    if task.exception():
                        raise task.exception()
                break
        except Exception as e:
            logger().logp(INFO, f"🔌 [PROXY] Lost WS connection [ID: {hex(id(client_ws))}] (Reason: {e})")
            attempt += 1
            if attempt >= max_retries:
                try:
                    await client_ws.close(code=1011)
                except Exception:
                    pass
                break
            await asyncio.sleep(retry_delay)


@router.post("/viz/app/paraview/")
async def viz_app_paraview_probe(request: Request):
    try:
        await request.body()
    except Exception:
        pass
    return Response(status_code=200, content="")


@router.api_route("/viz/app/{path:path}")
async def viz_proxy(
    request: Request,
    path: str,
    room_token: str = Cookie(None),
):
    if not room_token:
        raise HTTPException(status_code=401, detail="Missing room_token cookie")

    host = get_pool().get_pod_dns_for_token(room_token)
    if not host:
        raise HTTPException(status_code=503, detail="Viz service not ready yet")

    proxy_url = f"http://{host}:{_VIZ_PORT}"
    max_retries = 5
    query_string = request.url.query
    target_url = f"/{path}" + (f"?{query_string}" if query_string else "")

    try:
        req_body = await request.body()
    except ClientDisconnect:
        logger().logp(DEBUG, f"Client disconnected before body was read (viz proxy: {path})")
        return Response(status_code=499)
    proxy_headers = dict(request.headers)
    proxy_headers.pop("host", None)

    for attempt in range(max_retries):
        try:
            rp = await httpx_client.request(
                request.method,
                f"{proxy_url}{target_url}",
                headers=proxy_headers,
                content=req_body,
                timeout=5.0,
            )
            if rp.status_code in (301, 302, 303, 307, 308):
                location = rp.headers.get("location")
                if location:
                    new_location = f"/viz/app/{location.lstrip('/')}"
                    return Response(status_code=rp.status_code, headers={"Location": new_location})

            excluded_headers = {"transfer-encoding", "content-encoding", "content-length"}
            response_headers = {
                k: v for k, v in rp.headers.items() if k.lower() not in excluded_headers
            }
            if "trame" in path and path.endswith(('.js', '.css', '.woff2', '.ttf', '.png', '.jpg')):
                response_headers["cache-control"] = "public, max-age=86400, immutable"
            return Response(content=rp.content, status_code=rp.status_code, headers=response_headers)

        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5)
            else:
                logger().logp(ERROR, f"Viz proxy failed after {max_retries} attempts: {e} on {target_url}")
        except Exception as e:
            logger().logp(ERROR, f"Viz proxy unexpected error on {target_url}: {e}")
            break

    raise HTTPException(status_code=503, detail="Viz service unavailable")

@router.get("/viz/config/{path:path}")
async def serve_viz_config(path: str):
    """Serve static viz configuration files (CSS, fonts, etc.) directly."""
    allowed_extensions = {'.css', '.woff', '.woff2', '.ttf', '.eot', '.svg', '.png', '.jpg', '.ico', '.js'}

    # Look for file in viz_service config directory (correct path resolution)
    viz_config_dir = Path(__file__).resolve().parents[2] / "viz_service" / "viz_renderer" / "config"
    # JOIN the path before sanitizing
    full_path = (viz_config_dir / path)
    try:
        safe_path = sanitize_file_path(full_path, viz_config_dir)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid path")

    if safe_path.suffix.lower() not in allowed_extensions:
        raise HTTPException(status_code=403, detail="File type not allowed")

    if not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    content_type, _ = mimetypes.guess_type(str(safe_path))
    if content_type is None:
        content_type = "application/octet-stream"

    return FileResponse(safe_path, media_type=content_type)


# ---- Kedro Viz proxy ----

@router.api_route("/kedro-viz/{path:path}")
async def kedro_viz_proxy(
    request: Request,
    path: str = "",
    room_token: str = Cookie(None),
):
    """Proxy /kedro-viz/* to viz service for CSS injection and label replacement."""
    # NOTE: It's expected for the frontend to see HTTP 503 responses here while
    # Kedro Viz is starting or the Viz pod is initializing. The UI polls
    # endpoints such as `/api/main` and `/api/reload` and will retry until the
    # service is ready. Treat 503 responses during boot/connect as non-fatal
    # transient conditions rather than hard failures.
    if not room_token:
        raise HTTPException(status_code=401, detail="Missing room_token cookie")

    host = get_pool().get_pod_dns_for_token(room_token)
    if not host:
        raise HTTPException(status_code=503, detail="Viz service not ready yet")

    proxy_url = f"https://{host}:{_CMD_PORT}/viz/kedro-viz/{path}"
    if request.url.query:
        proxy_url += f"?{request.url.query}"

    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("Host", None)

    try:
        body = await request.body() if request.method in ["POST", "PUT"] else None
        response = await httpx_client.request(
            method=request.method, url=proxy_url, headers=headers, content=body, timeout=10.0
        )
        resp_headers = {
            k: v for k, v in response.headers.items() if k.lower() != "transfer-encoding"
        }
        return Response(content=response.content, status_code=response.status_code, headers=resp_headers)

    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Kedro Viz proxy error: {e}")


@router.api_route("/api/{path:path}")
async def kedro_viz_api_proxy(
    request: Request,
    path: str = "",
    room_token: str = Cookie(None),
):
    """Proxy /api/* requests to Kedro Viz."""
    if not room_token:
        raise HTTPException(status_code=401, detail="Missing room_token cookie")

    host = get_pool().get_pod_dns_for_token(room_token)
    if not host:
        raise HTTPException(status_code=503, detail="Viz service not ready yet")

    proxy_url = f"https://{host}:{_CMD_PORT}/viz/kedro-viz/api/{path}"
    if request.url.query:
        proxy_url += f"?{request.url.query}"

    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("Host", None)

    max_retries = 3
    last_error = None
    PROXY_TIMEOUT = 5.0
    body = await request.body() if request.method in ["POST", "PUT"] else None

    for attempt in range(max_retries):
        try:
            response = await httpx_client.request(
                method=request.method, url=proxy_url, headers=headers, content=body, timeout=PROXY_TIMEOUT
            )
            resp_headers = {
                k: v for k, v in response.headers.items() if k.lower() != "transfer-encoding"
            }
            return Response(content=response.content, status_code=response.status_code, headers=resp_headers)

        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            last_error = e
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5)
        except httpx.RequestError as e:
            last_error = e
            logger().logp(ERROR, f"Kedro Viz API proxy fatal error: {e}")
            break

    raise HTTPException(status_code=503, detail=f"Kedro Viz unavailable: {str(last_error)}")
