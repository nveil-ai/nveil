# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Data management routes -- thin proxy to file_service.

Server handles: user auth, room lookup (for viz host/port), then forwards
to file_service via ServiceClient. File CRUD operations (list, upload,
delete, rename, reupload) and room linking (link/unlink) all go through
the file service.
"""

import os
from typing import List

from database.core.database import db
from database.core.dependencies import get_file_service, get_room_service
from database.models import user
from database.services.file_service import FileService
from database.services.room_service import RoomService
from database.services.license_provider import license_provider
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from logger import INFO, logger
from pydantic import BaseModel
from shared.service_client import ServiceClient
from user_management.authentification import get_current_user
from utils import get_secret
from websocket_manager import ws_manager

FILE_HOST = get_secret("FILE_HOST", "localhost")
FILE_PORT = int(get_secret("FILE_PORT", "8200"))

# Maximum file size per file (1000 MB)
MAX_FILE_SIZE = 1000 * 1024 * 1024

# Mapping of file extensions to license feature names
EXTENSION_TO_FEATURE = {
    ".csv": "csv",
    ".xlsx": "xlsx",
    ".xls": "xlsx",
    ".ods": "xlsx",
    ".xlsm": "xlsx",
    ".mhd": "mhd",
    ".zraw": "mhd",
    ".json": "json",
    ".dcm": "dicom",
    ".edf": "edf",
    ".mat": "connectors",
    ".xml": "connectors",
}

_file_client = ServiceClient(verify=True)

router = APIRouter()


def _file_url(path: str) -> str:
    return f"https://{FILE_HOST}:{FILE_PORT}{path}"


# ------------------------------------------------------------------
# List user's files (proxy)
# ------------------------------------------------------------------


@router.get("/server/data/list")
async def list_user_files(
    current_user: user.User = Depends(get_current_user),
):
    """List all files owned by the current user."""
    owner_id = str(current_user.id)
    resp = await _file_client.get(
        _file_url(f"/file/data/list/{owner_id}"),
        headers={"X-Owner-Id": owner_id},
    )
    return JSONResponse(content=resp.data, status_code=resp.status_code or 200)


# ------------------------------------------------------------------
# Upload to user data store (proxy)
# ------------------------------------------------------------------


@router.post("/server/data/upload")
async def upload_to_store(
    files: list[UploadFile] = File(...),
    connector: str | None = Form(None),
    sequence_time_mode: str | None = Form(None),
    sequence_time_delta: str | None = Form(None),
    current_user: user.User = Depends(get_current_user),
):
    """Upload files to user data store (not tied to a room)."""
    if current_user.is_guest:
        raise HTTPException(
            status_code=403, detail="Guest users cannot upload files."
        )

    owner_id = str(current_user.id)

    license_info = await license_provider.get_license_info(owner_id)
    features = license_info.get("features", {}) if license_info else {}

    upload_limit_raw = features.get("upload")
    if upload_limit_raw is not None:
        try:
            user_max_size = int(float(upload_limit_raw)) * 1024 * 1024
        except (ValueError, TypeError):
            user_max_size = MAX_FILE_SIZE
    else:
        user_max_size = MAX_FILE_SIZE
    effective_max_size = min(MAX_FILE_SIZE, user_max_size)

    # Build multipart form data for forwarding
    file_tuples = []
    for f in files:
        # Check file type is allowed by license
        ext = os.path.splitext(f.filename)[1].lower()
        feature_name = EXTENSION_TO_FEATURE.get(ext)
        if feature_name:
            feature_val = features.get(feature_name)
            if feature_val is not None and str(feature_val).lower() == "false":
                logger().logp(INFO, f"[Upload] User {owner_id[:8]}.. file type '{ext}' not allowed by license")
                raise HTTPException(
                    status_code=403,
                    detail=f"File type '{ext}' is not available with your current plan. Please upgrade to upload {ext.upper()} files."
                )
        else:
            raise HTTPException(
                status_code=400, detail=f"File type '{ext}' is not supported."
            )

        content = await f.read()

        # Check file size against license limit
        if len(content) > effective_max_size:
            raise HTTPException(
                status_code=413,
                detail=f"File '{f.filename}' exceeds your plan's upload limit of {effective_max_size // (1024 * 1024)} MB."
            )

        file_tuples.append(("files", (f.filename, content, f.content_type or "application/octet-stream")))

    # Forward connector parameter as form data alongside files
    form_data = {}
    if connector:
        form_data["connector"] = connector
    if sequence_time_mode:
        form_data["sequence_time_mode"] = sequence_time_mode
    if sequence_time_delta:
        form_data["sequence_time_delta"] = sequence_time_delta
    resp = await _file_client.post(
        _file_url("/file/data/upload"),
        files=file_tuples,
        data=form_data,
        headers={"X-Owner-Id": owner_id},
        timeout=600.0,
    )

    # ServiceClient already parsed the body into resp.data (dict if JSON, str otherwise).
    status_code = resp.status_code or (200 if resp.ok else 502)
    body = resp.data if isinstance(resp.data, dict) else {
        "status": "error",
        "message": resp.data or resp.error or "Upload failed",
    }
    return JSONResponse(content=body, status_code=status_code)


# ------------------------------------------------------------------
# Accepted extensions (proxy) — single source of truth for frontends
# ------------------------------------------------------------------


@router.get("/server/extensions")
async def list_extensions(
    current_user: user.User = Depends(get_current_user),
):
    """Return all accepted file extensions (from file_service)."""
    resp = await _file_client.get(
        _file_url("/file/extensions"),
        headers={"X-Owner-Id": str(current_user.id)},
    )
    return JSONResponse(content=resp.data, status_code=resp.status_code or 200)


# ------------------------------------------------------------------
# Connector matching (proxy)
# ------------------------------------------------------------------


@router.get("/server/connectors/match")
async def match_connectors(
    extensions: str,
    current_user: user.User = Depends(get_current_user),
):
    """Return connectors compatible with the given file extensions."""
    resp = await _file_client.get(
        _file_url(f"/file/connectors/match?extensions={extensions}"),
        headers={"X-Owner-Id": str(current_user.id)},
    )
    return JSONResponse(content=resp.data, status_code=resp.status_code or 200)


# ------------------------------------------------------------------
# Upload from URL (proxy)
# ------------------------------------------------------------------


class UrlUploadRequest(BaseModel):
    urls: List[dict]


@router.post("/server/data/upload-url")
async def upload_from_url(
    body: UrlUploadRequest,
    current_user: user.User = Depends(get_current_user),
):
    """Download files from URLs and save to user data store."""
    if current_user.is_guest:
        raise HTTPException(
            status_code=403, detail="Guest users cannot upload files."
        )

    resp = await _file_client.post(
        _file_url("/file/data/upload-url"),
        json={"urls": body.urls},
        headers={"X-Owner-Id": str(current_user.id)},
        timeout=120.0,
    )
    return JSONResponse(content=resp.data, status_code=resp.status_code or 200)


# ------------------------------------------------------------------
# Delete a user file (proxy)
# ------------------------------------------------------------------


@router.delete("/server/data/{file_id}")
async def delete_user_file(
    file_id: str,
    current_user: user.User = Depends(get_current_user),
):
    # Phase 1 — file_service HTTP call with no DB session held
    resp = await _file_client.request(
        "DELETE",
        _file_url(f"/file/data/{file_id}"),
        headers={"X-Owner-Id": str(current_user.id)},
    )

    data = resp.data or {}

    # Phase 2 — short DB read for affected rooms (only if anything was affected)
    if resp.ok:
        affected = data.get("affected_room_ids", [])
        if affected:
            tokens_to_notify = []
            async with db.session() as session:
                room_service = RoomService(session)
                for rid in affected:
                    room = await room_service.room_repo.get_by_id(rid)
                    if room and room.token:
                        tokens_to_notify.append(str(room.token))

            # Phase 3 — WS sends with no DB session held
            for token in tokens_to_notify:
                await ws_manager.send(token, {
                    "event": "source_deleted",
                    "file_id": file_id,
                    "file_name": data.get("file_name", ""),
                })

    return JSONResponse(content=data, status_code=resp.status_code or 200)


# ------------------------------------------------------------------
# Rename (proxy)
# ------------------------------------------------------------------


class RenameRequest(BaseModel):
    display_name: str


@router.put("/server/data/{file_id}/rename")
async def rename_file(
    file_id: str,
    body: RenameRequest,
    current_user: user.User = Depends(get_current_user),
):
    resp = await _file_client.request(
        "PUT",
        _file_url(f"/file/data/{file_id}/rename"),
        json={"display_name": body.display_name},
        headers={"X-Owner-Id": str(current_user.id)},
    )
    return JSONResponse(content=resp.data, status_code=resp.status_code or 200)


# ------------------------------------------------------------------
# Re-upload content (proxy + WS notification)
# ------------------------------------------------------------------


@router.post("/server/data/{file_id}/reupload")
async def reupload_file(
    file_id: str,
    file: UploadFile = File(...),
    current_user: user.User = Depends(get_current_user),
):
    owner_id = str(current_user.id)
    # Phase 1 — file IO + forward to file_service with no DB session held
    content = await file.read()

    svc_resp = await _file_client.request(
        "POST",
        _file_url(f"/file/data/{file_id}/reupload"),
        files=[("file", (file.filename, content, file.content_type or "application/octet-stream"))],
        headers={"X-Owner-Id": owner_id},
    )

    data = svc_resp.data if isinstance(svc_resp.data, dict) else {"status": "error"}
    status_code = svc_resp.status_code or 500

    if status_code == 200:
        # Phase 2 — short DB read: collect rooms to notify
        tokens_to_notify = []
        async with db.session() as session:
            file_service = FileService(session)
            room_service = RoomService(session)
            refs = await file_service.get_rooms_for_file(file_id)
            for ref in refs:
                room = await room_service.room_repo.get_by_id(str(ref.room_id))
                if room and room.token:
                    tokens_to_notify.append(str(room.token))

        # Phase 3 — WS sends with no DB session held
        for token in tokens_to_notify:
            await ws_manager.send(token, {
                "event": "data_stale",
                "file_id": file_id,
                "file_name": file.filename,
            })
        data["rooms_notified"] = len(tokens_to_notify)

    return JSONResponse(content=data, status_code=status_code)


@router.post("/server/data/{file_id}/refetch")
async def refetch_url_file(
    file_id: str,
    current_user: user.User = Depends(get_current_user),
):
    """Re-download a URL-sourced file from its original URL."""
    owner_id = str(current_user.id)

    # Phase 1 — file_service HTTP call with no DB session held (timeout 120s)
    resp = await _file_client.post(
        _file_url(f"/file/data/{file_id}/refetch"),
        headers={"X-Owner-Id": owner_id},
        timeout=120.0,
    )

    data = resp.data
    if (resp.status_code or 200) == 200:
        # Phase 2 — short DB read: collect rooms to notify
        tokens_to_notify = []
        async with db.session() as session:
            file_service = FileService(session)
            room_service = RoomService(session)
            refs = await file_service.get_rooms_for_file(file_id)
            for ref in refs:
                room = await room_service.room_repo.get_by_id(str(ref.room_id))
                if room and room.token:
                    tokens_to_notify.append(str(room.token))

        # Phase 3 — WS sends with no DB session held
        for token in tokens_to_notify:
            await ws_manager.send(token, {
                "event": "data_stale",
                "file_id": file_id,
            })
        data["rooms_notified"] = len(tokens_to_notify)

    return JSONResponse(content=data, status_code=resp.status_code or 200)


# ------------------------------------------------------------------
# Link/unlink files to rooms (proxy with room lookup)
# ------------------------------------------------------------------


class LinkFilesRequest(BaseModel):
    file_ids: List[str]


@router.post("/server/rooms/{room_id}/link-files")
async def link_files_to_room(
    room_id: str,
    body: LinkFilesRequest,
    current_user: user.User = Depends(get_current_user),
):
    """Link existing user files to a room and add them to the choregraph."""
    resp = await _file_client.post(
        _file_url(f"/file/rooms/{room_id}/link"),
        json={"file_ids": body.file_ids},
        headers={"X-Owner-Id": str(current_user.id)},
    )
    return JSONResponse(content=resp.data, status_code=resp.status_code or 200)


class ApplyFilesRequest(BaseModel):
    link_file_ids: List[str] = []
    unlink_file_ids: List[str] = []


@router.post("/server/rooms/{room_id}/apply-files")
async def apply_file_changes(
    room_id: str,
    body: ApplyFilesRequest,
    current_user: user.User = Depends(get_current_user),
):
    """Batch apply file link/unlink changes to a room."""
    resp = await _file_client.post(
        _file_url(f"/file/rooms/{room_id}/apply"),
        json={
            "link_file_ids": body.link_file_ids,
            "unlink_file_ids": body.unlink_file_ids,
        },
        headers={"X-Owner-Id": str(current_user.id)},
    )
    return JSONResponse(content=resp.data, status_code=resp.status_code or 200)


@router.delete("/server/rooms/{room_id}/unlink-file/{file_id}")
async def unlink_file_from_room(
    room_id: str,
    file_id: str,
    current_user: user.User = Depends(get_current_user),
):
    """Unlink a file from a room."""
    resp = await _file_client.request(
        "DELETE",
        _file_url(f"/file/rooms/{room_id}/unlink/{file_id}"),
        headers={"X-Owner-Id": str(current_user.id)},
    )
    return JSONResponse(content=resp.data, status_code=resp.status_code or 200)


# ------------------------------------------------------------------
# File usage (proxy)
# ------------------------------------------------------------------


@router.get("/server/data/{file_id}/usage")
async def file_usage(
    file_id: str,
    current_user: user.User = Depends(get_current_user),
):
    resp = await _file_client.get(
        _file_url(f"/file/data/{file_id}/usage"),
        headers={"X-Owner-Id": str(current_user.id)},
    )
    return JSONResponse(content=resp.data, status_code=resp.status_code or 200)
