# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""File management routes: metadata get/set, catalogue stats, artifact serving."""

import json
import math
import os

from database.core.dependencies import get_room_service
from database.services.room_service import RoomService
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from logger import ERROR, WARNING, logger
from shared.workspace import workspace_path as _workspace_path, DIVE_PATH

from shared.security import sanitize_file_path

router = APIRouter()

_ARTIFACT_SUFFIXES = {".png", ".jpg", ".jpeg", ".svg"}


@router.get("/server/rooms/{room_token}/artifacts/{filename}")
async def get_room_artifact(
    room_token: str,
    filename: str,
    room_service: RoomService = Depends(get_room_service),
):
    """Serve persisted room artifacts (viz thumbnails, exports).

    Path-based room_token auth so persisted chat HTML renders regardless
    of which room is currently cookie-active.
    """
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not any(filename.endswith(s) for s in _ARTIFACT_SUFFIXES):
        raise HTTPException(status_code=400, detail="Unsupported artifact type")

    room = await room_service.room_repo.get_by_token(room_token)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    artifact_path = _workspace_path(str(room.owner_id), str(room.id)) / "artifacts" / filename
    try:
        sanitize_file_path(str(artifact_path), DIVE_PATH)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")

    # Thumbnail may still be generating (async fire-and-forget on viz side).
    # Wait briefly instead of returning 404 — lets the browser's native <img>
    # loading work without any client-side retry logic.
    if not artifact_path.exists():
        import asyncio
        for _ in range(10):            # up to ~5 s
            await asyncio.sleep(0.5)
            if artifact_path.exists():
                break
        else:
            # no-store prevents Cloudflare from caching this transient 404
            return Response(status_code=404, headers={"Cache-Control": "no-store"})

    suffix = artifact_path.suffix.lower()
    media = {
        ".png": "image/png", ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg", ".svg": "image/svg+xml",
    }.get(suffix, "application/octet-stream")

    return FileResponse(
        str(artifact_path),
        media_type=media,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/server/files/get_metadata")
async def get_room_metadata(
    room_token: str = Cookie(None),
    room_id: str = Cookie(None),
    room_service: RoomService = Depends(get_room_service),
    metadata_name: str | None = Query(None),
):
    """Retrieve value from the JSON metadata file associated with the given room ID."""
    if room_token:
        room = await room_service.room_repo.get_by_token(room_token)
        if not room:
            logger().logp(WARNING, f"No rooms with token [{room_token}]")
            raise HTTPException(status_code=404, detail="Room not found.")
    elif room_id:
        room = await room_service.room_repo.get_by_id(room_id)
        if not room:
            logger().logp(WARNING, f"No rooms with ID [{room_id}]")
            raise HTTPException(status_code=404, detail="Room not found.")
    else:
        logger().logp(ERROR, f"No room identified for metadata retrieval.")
        if metadata_name:
            return JSONResponse(content={metadata_name: None})
        else:
            return JSONResponse(content={})

    metadata_file_path = str(_workspace_path(str(room.owner_id), str(room.id)) / "metadata.json")

    # Sanitize the metadata file path to prevent directory traversal
    try:
        sanitize_file_path(metadata_file_path, DIVE_PATH)
    except ValueError as e:
        logger().logp(ERROR, f"Invalid metadata file path: {e}")
        raise HTTPException(status_code=404, detail="Not Found")

    try:
        with open(metadata_file_path, "r") as f:
            data = json.load(f)
            if metadata_name:
                metadata_value = data.get(metadata_name, "")
                return JSONResponse(content={metadata_name: metadata_value})
            else:
                return JSONResponse(content=data)
    except FileNotFoundError:
        if metadata_name:
            return JSONResponse(content={metadata_name: None})
        else:
            return JSONResponse(content={})
    except Exception as e:
        logger().logp(ERROR, f"Error reading metadata file for room {room.id}: {e}")
        return JSONResponse(content={metadata_name: None})


@router.get("/server/files/get_catalogue_stats")
async def get_catalogue_stats(
    room_token: str = Cookie(None),
    room_id: str = Cookie(None),
    type: str = None,
    room_service: RoomService = Depends(get_room_service),
):
    """Return the catalogue_stats.json from the room's pipeline/cache directory."""
    if room_token:
        room = await room_service.room_repo.get_by_token(room_token)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found.")
    elif room_id:
        room = await room_service.room_repo.get_by_id(room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found.")
    else:
        return JSONResponse(content={"datasets": {}})

    stats_path = str(_workspace_path(str(room.owner_id), str(room.id)) / "pipeline" / "cache" / "catalogue_stats.json")

    # Sanitize the stats file path to prevent directory traversal
    try:
        sanitize_file_path(stats_path, DIVE_PATH)
    except ValueError as e:
        logger().logp(ERROR, f"Invalid stats file path: {e}")
        raise HTTPException(status_code=404, detail="Not Found")

    def _sanitize_floats(obj):
        """Replace NaN/Infinity with None so JSON serialization succeeds."""
        if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
            return None
        if isinstance(obj, dict):
            return {k: _sanitize_floats(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_sanitize_floats(v) for v in obj]
        return obj

    def _filter_by_type(data, dataset_type):
        """Filter datasets by type if a type filter is specified."""
        if not dataset_type:
            return data
        datasets = data.get("datasets", {})
        filtered = {k: v for k, v in datasets.items() if v.get("type") == dataset_type}
        return {**data, "datasets": filtered}

    try:
        with open(stats_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return JSONResponse(content=_sanitize_floats(_filter_by_type(data, type)))
    except FileNotFoundError:
        return JSONResponse(content={"datasets": {}})
    except json.JSONDecodeError:
        # catalogue_stats may contain Python-style NaN/Infinity literals
        try:
            import re
            with open(stats_path, "r", encoding="utf-8") as f:
                raw = f.read()
            raw = re.sub(r'\bNaN\b', 'null', raw)
            raw = re.sub(r'\bInfinity\b', 'null', raw)
            raw = re.sub(r'\b-Infinity\b', 'null', raw)
            data = json.loads(raw)
            return JSONResponse(content=_sanitize_floats(_filter_by_type(data, type)))
        except Exception as inner_e:
            logger().logp(ERROR, f"Error parsing catalogue_stats for room {room.id}: {inner_e}")
            return JSONResponse(content={"datasets": {}})
    except Exception as e:
        logger().logp(ERROR, f"Error reading catalogue_stats for room {room.id}: {e}")
        return JSONResponse(content={"datasets": {}})


@router.post("/server/files/set_metadata")
async def set_room_metadata(
    data: dict,
    room_token: str = Cookie(None),
    room_id: str = Cookie(None),
    room_service: RoomService = Depends(get_room_service),
):
    """Set value in the JSON metadata file associated with the given room ID."""
    if room_token:
        room = await room_service.room_repo.get_by_token(room_token)
        if not room:
            logger().logp(WARNING, f"No rooms with token [{room_token}]")
            raise HTTPException(status_code=404, detail="Room not found.")
    elif room_id:
        room = await room_service.room_repo.get_by_id(room_id)
        if not room:
            logger().logp(WARNING, f"No rooms with ID [{room_id}]")
            raise HTTPException(status_code=404, detail="Room not found.")
    else:
        logger().logp(ERROR, f"No room identified for metadata update.")
        raise HTTPException(status_code=400, detail="Missing room_token or room_id cookie.")

    metadata_file = str(_workspace_path(str(room.owner_id), str(room.id)) / "metadata.json")

    # Sanitize the metadata file path to prevent directory traversal
    try:
        sanitize_file_path(metadata_file, DIVE_PATH)
    except ValueError as e:
        logger().logp(ERROR, f"Invalid metadata file path: {e}")
        raise HTTPException(status_code=404, detail="Not Found")

    os.makedirs(os.path.dirname(metadata_file), exist_ok=True)

    if os.path.exists(metadata_file):
        try:
            with open(metadata_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception as e:
            logger().logp(ERROR, f"Failed to read metadata file: {e}")
            metadata = {}
    else:
        metadata = {}

    append = False
    if 'append' in data:
        append = bool(data.pop('append'))

    for key, value in data.items():
        if append:
            if key in metadata and isinstance(metadata[key], list):
                if isinstance(value, list):
                    metadata[key].extend(value)
                else:
                    metadata[key].append(value)
            else:
                metadata[key] = value
        else:
            metadata[key] = value

    try:
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        return JSONResponse(content={"status": "success"})
    except Exception as e:
        logger().logp(ERROR, f"Failed to write metadata file: {e}")
        raise HTTPException(status_code=500, detail="Failed to write metadata file.")
