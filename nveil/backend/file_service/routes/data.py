# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""File CRUD routes: upload, list, delete, rename, reupload."""

import json
import os
from pathlib import Path
from typing import List
from urllib.parse import unquote, urlparse

import httpx
from db.core.dependencies import get_file_manager
from db.core.database import db
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from logger import logger
from pydantic import BaseModel
from services.file_manager import FileManager
from shared.workspace import user_file_path
from shared.security import safe_path, sanitize_filename

log = logger()

# Shared async HTTP client, injected by file_server.lifespan via set_httpx_client.
# Reused for ai-service calls and for arbitrary user-supplied URL downloads —
# both benefit from connection pooling + HTTP/2 (where the peer supports it).
httpx_client: httpx.AsyncClient = None


def set_httpx_client(client: httpx.AsyncClient):
    global httpx_client
    httpx_client = client

from shared.secrets import get_secret

AI_HOST = get_secret("AI_HOST", "localhost")
AI_PORT = 8100

EXCEL_EXTENSIONS = {".xlsx", ".xls", ".ods", ".xlsm"}

# Native extensions handled by the app without a connector
NATIVE_EXTENSIONS = frozenset({
    ".csv", ".tsv", ".json", ".parquet",
    ".xlsx", ".xls", ".ods", ".xlsm",
    ".mhd", ".zraw",
    ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp", ".gif",
    ".dcm",
    ".edf",
})

router = APIRouter()


def _parse_companions(raw: str | None) -> list:
    if not raw:
        return []
    try:
        # We strictly prefer JSON for companion files
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        # Fallback to empty list instead of risky eval if JSON fails
        # This assumes companion_files should always be JSON-formatted
        log.warning("Failed to parse companion_files as JSON. Returning empty list.")
        return []


def _sanitize_filename(filename: str) -> str:
    sanitized = os.path.basename(filename)
    sanitized = "".join(c for c in sanitized if c.isalnum() or c in (".", "-", "_"))
    return sanitized


# ------------------------------------------------------------------
# List user's files
# ------------------------------------------------------------------


@router.get("/file/data/list/{owner_id}")
async def list_user_files(
    owner_id: str,
    x_owner_id: str = Header(..., alias="X-Owner-Id"),
    file_manager: FileManager = Depends(get_file_manager),
):
    """List all files owned by the given user."""
    # Sanitize inputs
    owner_id = sanitize_filename(owner_id)
    files = await file_manager.get_user_files(owner_id)
    result = []
    for f in files:
        refs = await file_manager.get_rooms_for_file(str(f.id))
        result.append({
            "id": str(f.id),
            "file_id": str(f.file_id),
            "original_name": f.original_name,
            "display_name": f.display_name or f.original_name,
            "format": f.format,
            "size_bytes": f.size_bytes,
            "companion_files": _parse_companions(f.companion_files),
            "processing_status": f.processing_status,
            "upload_source": f.upload_source,
            "source_url": f.source_url,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "updated_at": f.updated_at.isoformat() if f.updated_at else None,
            "room_count": len(refs),
            "linked_room_ids": [str(r.room_id) for r in refs],
            "collection_time_mode": f.collection_time_mode,
        })
    return JSONResponse(content={"files": result})


# ------------------------------------------------------------------
# Connector matching
# ------------------------------------------------------------------


@router.get("/file/extensions")
async def list_extensions():
    """Return all file extensions accepted by the platform.

    Combines natively supported extensions with those handled by connectors.
    This is the single source of truth — frontends should fetch from here
    instead of maintaining their own hardcoded lists.
    """
    from connectors import CONNECTOR_REGISTRY

    all_exts = set(NATIVE_EXTENSIONS)
    for meta in CONNECTOR_REGISTRY.values():
        all_exts.update(a.lower() for a in meta["accepts"])

    return JSONResponse(content={
        "extensions": sorted(all_exts),
    })


@router.get("/file/connectors/match")
async def match_connectors(extensions: str = Query(...)):
    """Return connectors compatible with the given file extensions.

    The frontend calls this when the user drops files to determine whether
    a connector dropdown should be shown.

    Query param ``extensions``: comma-separated list (e.g. ``.xml,.mat``).
    """
    from connectors import CONNECTOR_REGISTRY

    ext_set = {e.strip().lower() for e in extensions.split(",") if e.strip()}
    has_non_native = any(e not in NATIVE_EXTENSIONS for e in ext_set)

    matches = []
    for cid, meta in CONNECTOR_REGISTRY.items():
        accepts = {a.lower() for a in meta["accepts"]}
        if ext_set & accepts:
            matches.append({
                "id": cid,
                "label": meta["label"],
                "description": meta.get("description", ""),
                "required": meta["required"],
            })

    return JSONResponse(content={
        "connectors": matches,
        "all_native": not has_non_native,
    })


# ------------------------------------------------------------------
# Upload to user data store
# ------------------------------------------------------------------


def _compute_file_stats(
    owner_id: str, file_id: str, filenames: "str | list[str]",
    stats_filename: str | None = None,
):
    """Compute field metadata for one or more files and store as JSON.

    Delegates to ``choregraph.metadata.compute_file_stats`` which handles
    CSV, TSV, Parquet, JSON, images, and MHD files.  When a list of
    filenames is passed, stats are aggregated across all files.
    """
    from choregraph.metadata import compute_file_stats

    owner_id = sanitize_filename(owner_id)
    file_id = sanitize_filename(file_id)

    store_dir = user_file_path(owner_id, file_id)

    if isinstance(filenames, str):
        file_paths = str(safe_path(store_dir, sanitize_filename(filenames)))
        display_name = filenames
    else:
        file_paths = [str(safe_path(store_dir, sanitize_filename(fn))) for fn in filenames]
        display_name = filenames[0] if filenames else "?"

    safe_stats_name = sanitize_filename(stats_filename) if stats_filename else "file_stats.json"
    stats_path = safe_path(store_dir, safe_stats_name)

    try:
        stats = compute_file_stats(file_paths)
        if stats is None:
            return

        stats_path.write_text(json.dumps(stats, default=str), encoding="utf-8")
        n = len(filenames) if isinstance(filenames, list) else 1
        log.info(f"  Stats computed for '{display_name}' ({len(stats.get('fields', []))} fields, {n} file(s))")
    except Exception as e:
        log.warning(f"  Stats failed for '{display_name}': {e}")


async def _preprocess_excel(
    owner_id: str, file_id: str, user_file_id: str, filename: str,
    previous_companions: list | None = None,
):
    """Background task: call AI service to preprocess an Excel file."""
    log.info(f"EXCEL PREPROCESS start '{filename}' (file_id={file_id[:8]}..)")
    
    owner_id = sanitize_filename(owner_id)
    file_id = sanitize_filename(file_id)
    filename = sanitize_filename(filename)
    
    store_dir = user_file_path(owner_id, file_id)
    file_path = str(safe_path(store_dir, filename))

    # Extract table names from previous companion parquet filenames
    previous_names = None
    if previous_companions:
        previous_names = [
            os.path.splitext(c)[0] for c in previous_companions
            if c.endswith(".parquet")
        ]
        if previous_names:
            log.info(f"  Passing {len(previous_names)} previous name hint(s): {previous_names}")

    try:
        payload = {
            "file_path": file_path,
            "owner_id": owner_id,
            "file_id": file_id,
        }
        if previous_names:
            payload["previous_names"] = previous_names

        url = f"https://{AI_HOST}:{AI_PORT}/ai/preprocess_excel"
        log.info(f"  Calling AI service: {url}")
        resp = await httpx_client.post(url, json=payload, timeout=600.0)
        resp.raise_for_status()
        result = resp.json()

        companion_files = result.get("companion_files", [])
        status = "ready" if result.get("status") == "ok" else "error"
        log.success(f"EXCEL PREPROCESS done '{filename}' → status={status}, companions={companion_files}")

        # Compute metadata for companion parquets
        for cf in companion_files:
            if cf.endswith(".parquet"):
                stem = os.path.splitext(cf)[0]
                _compute_file_stats(
                    owner_id, file_id, cf,
                    stats_filename=f"{stem}_file_stats.json",
                )
    except Exception as e:
        log.error(f"EXCEL PREPROCESS failed '{filename}': {e}")
        companion_files = []
        status = "error"

    # Update DB record in a fresh session
    async with db.session() as session:
        fm = FileManager(session)
        await fm.update_processing_status(user_file_id, status, companion_files or None)


async def _preprocess_connector(
    owner_id: str, file_id: str, user_file_id: str, connector: str,
    sequence_time_mode: str | None = None,
):
    """Background task: run a connector conversion (e.g. PhysiCell .mat → CSV)."""
    log.info(f"CONNECTOR PREPROCESS start connector={connector} (file_id={file_id[:8]}..)")
    
    owner_id = sanitize_filename(owner_id)
    file_id = sanitize_filename(file_id)
    store_dir = safe_path(user_file_path(owner_id, file_id), ".")

    try:
        if connector == "physicell":
            from connectors.physicell import convert
            from connectors.physicell.xml_parser import is_physicell_xml, extract_time_from_xml

            # Find ALL PhysiCell XMLs in the store directory
            xml_paths = sorted(
                entry.path for entry in os.scandir(store_dir)
                if entry.is_file() and entry.name.lower().endswith(".xml") and is_physicell_xml(entry.path)
            )
            if not xml_paths:
                raise ValueError("No PhysiCell XML file found in uploaded files")

            # Convert each snapshot
            companion_files = []
            timestamps = []
            time_units = "min"
            for xml_path in xml_paths:
                csv_paths = convert(xml_path, str(store_dir))
                companion_files.extend(os.path.basename(p) for p in csv_paths)

                sim_time, units = extract_time_from_xml(xml_path)
                if sim_time is not None:
                    timestamps.append(sim_time)
                    time_units = units

            log.success(f"CONNECTOR PREPROCESS done → {len(companion_files)} CSV(s) from {len(xml_paths)} snapshot(s)")

            # Temporal detection: user explicitly chose sequence OR 2+ snapshots
            is_temporal = len(xml_paths) >= 2 or sequence_time_mode is not None
            temporal_time_mode = None
            temporal_time_delta = None

            if is_temporal:
                # Try to infer timing from XML timestamps
                if len(timestamps) >= 2:
                    timestamps.sort()
                    deltas = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]
                    deltas = [d for d in deltas if d > 0]
                    if deltas:
                        median_delta = sorted(deltas)[len(deltas) // 2]
                        UNIT_TO_SECONDS = {"sec": 1, "s": 1, "min": 60, "hour": 3600, "h": 3600, "day": 86400, "d": 86400}
                        spu = UNIT_TO_SECONDS.get(time_units.lower(), 60)
                        temporal_time_delta = f"PT{int(median_delta * spu)}S"
                        temporal_time_mode = "time_based"
                        log.info(f"  PhysiCell temporal: {len(timestamps)} snapshots, delta={median_delta} {time_units} → {temporal_time_delta}")

                # Fallback: user chose auto or index, or inference failed
                if not temporal_time_mode:
                    if sequence_time_mode == "auto" or sequence_time_mode == "time_based":
                        temporal_time_mode = "time_based"
                    else:
                        temporal_time_mode = sequence_time_mode or "index"

            # Group CSVs by type for metadata computation
            # Pass all files in each group so stats aggregate across snapshots
            seen_suffixes = set()
            cells_csvs = sorted(f for f in companion_files if "_cells.csv" in f)
            microenv_csvs = sorted(f for f in companion_files if "_microenvironment.csv" in f)

            for group_name, group_files in [("cells", cells_csvs), ("microenvironment", microenv_csvs)]:
                if group_files:
                    first = group_files[0]
                    _compute_file_stats(
                        owner_id, file_id, group_files,
                        stats_filename=f"{os.path.splitext(first)[0]}_file_stats.json",
                    )
                    seen_suffixes.add(group_name)

            # Compute stats for any other CSVs not in cells/microenv groups
            for cf in companion_files:
                if "_cells.csv" not in cf and "_microenvironment.csv" not in cf:
                    _compute_file_stats(
                        owner_id, file_id, cf,
                        stats_filename=f"{os.path.splitext(cf)[0]}_file_stats.json",
                    )

            # Store temporal config on the UserFile record
            if temporal_time_mode:
                async with db.session() as session:
                    fm = FileManager(session)
                    await fm.file_repo.update_by_id(
                        user_file_id,
                        collection_time_mode=temporal_time_mode,
                        collection_time_delta=temporal_time_delta,
                    )
                    await session.commit()
        else:
            raise ValueError(f"Unknown connector: {connector}")

        status = "ready"
    except Exception as e:
        log.error(f"CONNECTOR PREPROCESS failed: {e}")
        companion_files = []
        status = "error"

    # Update DB record in a fresh session
    async with db.session() as session:
        fm = FileManager(session)
        await fm.update_processing_status(user_file_id, status, companion_files or None)


async def _rebuild_catalogues_for_file(owner_id: str, user_file_id: str):
    """Refresh each linked room's ``catalogue_stats.json`` entry for this file.

    Re-upload / Excel preprocess overwrites ``file_stats.json`` inside
    the file's data store, but each room caches a merged view in its
    own ``pipeline/cache/catalogue_stats.json``.  Without this trigger,
    the frontend keeps showing the stale pre-reupload metadata (types,
    min/max) until the user manually re-links.

    Uses ``Metadata.merge_datasets`` to update only the affected
    dataset's entry per room — no full rebuild, no re-reading of other
    files' stats.

    Runs as a background task **after** ``_compute_file_stats``.
    """
    from choregraph.metadata import Metadata
    from routes.rooms import _get_choregraph_input_ids
    from shared.workspace import workspace_path as _workspace_path

    try:
        async with db.session() as session:
            fm = FileManager(session)
            uf = await fm.get_file_by_id(user_file_id)
            if not uf:
                return

            store_dir = user_file_path(owner_id, str(uf.file_id))
            dataset_name = os.path.splitext(uf.original_name)[0]

            # Collect this file's updated stats (primary + companions).
            entries: dict = {}
            fstats_path = store_dir / "file_stats.json"
            if fstats_path.exists():
                try:
                    fstats = json.loads(fstats_path.read_text(encoding="utf-8"))
                    fstats.setdefault("type", "input")
                    entries[dataset_name] = fstats
                except Exception:
                    pass

            if uf.companion_files:
                try:
                    companions = (
                        json.loads(uf.companion_files)
                        if isinstance(uf.companion_files, str)
                        else uf.companion_files
                    )
                except Exception:
                    companions = []
                for cf in companions or []:
                    cf_stem = os.path.splitext(cf)[0]
                    cf_stats = store_dir / f"{cf_stem}_file_stats.json"
                    if cf_stats.exists():
                        try:
                            fstats = json.loads(cf_stats.read_text(encoding="utf-8"))
                            fstats.setdefault("type", "input")
                            entries[cf_stem] = fstats
                        except Exception:
                            pass

            if not entries:
                return

            # Fan out to every linked room — rooms own their catalogue.
            room_refs = await fm.get_rooms_for_file(user_file_id)
            for rref in room_refs:
                room_id = str(rref.room_id)
                ws = _workspace_path(owner_id, room_id)
                if not ws.exists():
                    continue
                try:
                    # IDs come from the room's choregraph.xml so the entry
                    # keys match the asp / dive layer's expectations.
                    input_ids = _get_choregraph_input_ids(ws)
                    scoped = {
                        name: {**e, "id": input_ids.get(name)}
                        for name, e in entries.items()
                    }
                    Metadata(workspace_path=ws).merge_datasets(scoped)
                    log.info(
                        f"  Catalogue refreshed post-reupload "
                        f"(room={room_id[:8]}.., {len(scoped)} entry/ies)"
                    )
                except Exception as e:
                    log.warning(f"  Catalogue refresh failed for room {room_id[:8]}..: {e}")
    except Exception as e:
        log.error(f"_rebuild_catalogues_for_file failed: {e}")


def _queue_post_upload_tasks(
    background_tasks: BackgroundTasks,
    owner_id: str,
    file_id: str,
    user_file_id: str,
    filenames: "str | list[str]",
    previous_companions: list | None = None,
):
    """Queue metadata computation and Excel preprocessing after upload/reupload.

    For non-Excel files, ``_compute_file_stats`` runs first (writes
    ``file_stats.json``), then ``_rebuild_catalogues_for_file`` merges
    the fresh stats into every linked room's ``catalogue_stats.json``.
    FastAPI background tasks run sequentially in the order they're added.
    """
    primary = filenames[0] if isinstance(filenames, list) else filenames
    ext = os.path.splitext(primary)[1].lower()
    if ext not in EXCEL_EXTENSIONS:
        background_tasks.add_task(
            _compute_file_stats, owner_id=owner_id, file_id=file_id, filenames=filenames,
        )
        background_tasks.add_task(
            _rebuild_catalogues_for_file, owner_id=owner_id, user_file_id=user_file_id,
        )
    else:
        log.info(f"  Excel detected ({ext}), queuing background preprocessing")
        background_tasks.add_task(
            _preprocess_excel, owner_id=owner_id, file_id=file_id,
            user_file_id=user_file_id, filename=primary,
            previous_companions=previous_companions,
        )
        # Excel preprocess also updates file_stats; rebuild catalogues after.
        background_tasks.add_task(
            _rebuild_catalogues_for_file, owner_id=owner_id, user_file_id=user_file_id,
        )


@router.post("/file/data/upload")
async def upload_to_store(
    files: list[UploadFile] = File(...),
    x_owner_id: str = Header(..., alias="X-Owner-Id"),
    connector: str | None = Form(None),
    sequence_time_mode: str | None = Form(None),
    sequence_time_delta: str | None = Form(None),
    file_manager: FileManager = Depends(get_file_manager),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Upload files to user data store (not tied to a room).

    When ``connector`` is provided (e.g. ``"physicell"``), files are grouped
    into a single record: the XML is the primary file, .mat files are stored
    as companions.  A background task converts them to CSVs.

    When ``sequence_time_mode`` is provided (``"index"``, ``"time_based"``,
    or ``"auto"``), the uploaded files are stored as ONE record with
    companions (like DICOM) and temporal metadata on the UserFile.
    """
    log.info(
        f"UPLOAD owner={x_owner_id[:8]}.. {len(files)} file(s): "
        f"{', '.join(f.filename for f in files)}"
        f"{f' connector={connector}' if connector else ''}"
    )

    # --- Connector upload: group all files into one record ---
    if connector:
        return await _upload_with_connector(
            files, x_owner_id, connector, file_manager, background_tasks,
            sequence_time_mode=sequence_time_mode,
        )

    # --- Temporal sequence: ONE record with companions (like DICOM) ---
    if sequence_time_mode and len(files) >= 2:
        return await _upload_as_temporal_collection(
            files, x_owner_id, sequence_time_mode, sequence_time_delta,
            file_manager, background_tasks,
        )

    # --- Group companion files (e.g. MHD + ZRAW) before the per-file loop ---
    from services.file_manager import COMPANION_MAP

    # Build reverse map: companion ext → primary ext
    _companion_to_primary = {}
    for prim_ext, comp_exts in COMPANION_MAP.items():
        for ce in comp_exts:
            _companion_to_primary[ce] = prim_ext

    # Bucket files: {primary_filename: {"primary": UploadFile, "companions": [UploadFile]}}
    groups: dict[str, dict] = {}
    standalone: list[UploadFile] = []

    # First pass: identify primaries
    primary_stems: dict[str, str] = {}  # stem → sanitized primary name
    for f in files:
        if not f.filename:
            continue
        sanitized = sanitize_filename(f.filename)
        if not sanitized:
            raise HTTPException(status_code=400, detail=f"Invalid filename: '{f.filename}'")
        ext = os.path.splitext(sanitized)[1].lower()
        if ext in COMPANION_MAP:
            stem = os.path.splitext(sanitized)[0]
            primary_stems[stem] = sanitized
            groups[sanitized] = {"primary": f, "companions": []}

    # Second pass: match companions to their primary
    for f in files:
        if not f.filename:
            continue
        sanitized = sanitize_filename(f.filename)
        if not sanitized:
            continue
        ext = os.path.splitext(sanitized)[1].lower()
        if ext in _companion_to_primary:
            stem = os.path.splitext(sanitized)[0]
            primary_name = primary_stems.get(stem)
            if primary_name and primary_name in groups:
                groups[primary_name]["companions"].append(f)
                continue
        # Not a matched companion and not already a primary
        if sanitized not in groups:
            standalone.append(f)

    # --- Normal upload: one record per file (or per companion group) ---
    uploaded = []

    # Upload companion groups (e.g. scan.mhd + scan.zraw → one record)
    for primary_name, group in groups.items():
        primary_data = await group["primary"].read()
        companions = {}
        for cf in group["companions"]:
            cname = sanitize_filename(cf.filename)
            companions[cname] = await cf.read()

        existing = await file_manager.file_repo.get_by_owner_and_name(x_owner_id, primary_name)
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"A file named '{primary_name}' already exists. Rename it or use the re-upload button in My Files.",
            )

        record = await file_manager.upload_to_store(
            owner_id=x_owner_id,
            filename=primary_name,
            data=primary_data,
            companions=companions if companions else None,
        )
        all_names = [primary_name] + list(companions.keys())
        log.success(f"  Stored '{primary_name}' + {len(companions)} companion(s) → file_id={str(record.file_id)[:8]}..")
        uploaded.append({
            "id": str(record.id),
            "file_id": str(record.file_id),
            "original_name": record.original_name,
            "processing_status": record.processing_status,
        })

        _queue_post_upload_tasks(
            background_tasks, x_owner_id,
            file_id=str(record.file_id),
            user_file_id=str(record.id),
            filenames=all_names,
        )

    # Upload standalone files (no companion grouping)
    for file in standalone:
        sanitized = sanitize_filename(file.filename)
        if not sanitized:
            continue

        existing = await file_manager.file_repo.get_by_owner_and_name(x_owner_id, sanitized)
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"A file named '{sanitized}' already exists. Rename it or use the re-upload button in My Files.",
            )

        data = await file.read()
        record = await file_manager.upload_to_store(
            owner_id=x_owner_id,
            filename=sanitized,
            data=data,
        )
        log.success(f"  Stored '{sanitized}' ({len(data)} bytes) → file_id={str(record.file_id)[:8]}..")
        uploaded.append({
            "id": str(record.id),
            "file_id": str(record.file_id),
            "original_name": record.original_name,
            "processing_status": record.processing_status,
        })

        _queue_post_upload_tasks(
            background_tasks, x_owner_id,
            file_id=str(record.file_id),
            user_file_id=str(record.id),
            filenames=sanitized,
        )

    return JSONResponse(content={"status": "ok", "files": uploaded})


async def _upload_as_temporal_collection(
    files: list[UploadFile],
    owner_id: str,
    time_mode: str,
    time_delta: str | None,
    file_manager: FileManager,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    """Upload multiple files as ONE temporal collection record.

    Follows the DICOM pattern: first file (sorted by name) is primary,
    rest are companions stored in the same directory.
    """
    # Read all files and sort by name for natural ordering
    file_data: list[tuple[str, bytes]] = []
    for f in files:
        sanitized = _sanitize_filename(f.filename)
        if not sanitized:
            raise HTTPException(status_code=400, detail=f"Invalid filename: '{f.filename}'")
        data = await f.read()
        file_data.append((sanitized, data))

    file_data.sort(key=lambda x: x[0])

    primary_name, primary_data = file_data[0]
    companions = {name: data for name, data in file_data[1:]}

    # Check for existing file with same name
    existing = await file_manager.file_repo.get_by_owner_and_name(owner_id, primary_name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A file named '{primary_name}' already exists.",
        )

    record = await file_manager.upload_to_store(
        owner_id=owner_id,
        filename=primary_name,
        data=primary_data,
        companions=companions,
    )

    # Set temporal metadata on the record
    is_auto = time_mode == "auto"
    effective_mode = "index" if is_auto else time_mode
    await file_manager.file_repo.update_by_id(
        str(record.id),
        collection_time_mode=effective_mode,
        collection_time_delta=time_delta,
    )
    await file_manager.session.commit()

    log.success(
        f"  Temporal collection '{primary_name}' + {len(companions)} companion(s) "
        f"→ file_id={str(record.file_id)[:8]}.. mode={time_mode}"
    )

    # Compute file stats aggregated across all files in the collection
    all_filenames = [primary_name] + list(companions.keys())
    _queue_post_upload_tasks(
        background_tasks, owner_id,
        file_id=str(record.file_id),
        user_file_id=str(record.id),
        filenames=all_filenames,
    )

    uploaded = [{
        "id": str(record.id),
        "file_id": str(record.file_id),
        "original_name": record.original_name,
        "processing_status": record.processing_status,
    }]


    return JSONResponse(content={"status": "ok", "files": uploaded})


async def _upload_with_connector(
    files: list[UploadFile],
    owner_id: str,
    connector: str,
    file_manager: FileManager,
    background_tasks: BackgroundTasks,
    sequence_time_mode: str | None = None,
) -> JSONResponse:
    """Handle upload with a connector: group files, store, run conversion.

    When *sequence_time_mode* is set (e.g. ``"auto"``), the connector
    preprocessing will detect temporal sequences and set collection
    metadata on the UserFile record.
    """

    # --- DICOM connector: group all .dcm files as one series ---
    if connector == "dicom":
        return await _upload_dicom_series(
            files, owner_id, file_manager, background_tasks,
        )

    # Identify primary file (XML for physicell) and companions (.mat)
    primary_file = None
    companion_files: dict[str, bytes] = {}

    for file in files:
        if not file.filename:
            continue
        sanitized = sanitize_filename(file.filename)
        data = await file.read()
        ext = os.path.splitext(sanitized)[1].lower()

        if ext == ".xml" and primary_file is None:
            primary_file = (sanitized, data)
        else:
            companion_files[sanitized] = data

    if primary_file is None:
        raise HTTPException(
            status_code=400,
            detail="Connector upload requires an XML metadata file.",
        )

    primary_name, primary_data = primary_file

    existing = await file_manager.file_repo.get_by_owner_and_name(owner_id, primary_name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A file named '{primary_name}' already exists.",
        )

    record = await file_manager.upload_to_store(
        owner_id=owner_id,
        filename=primary_name,
        data=primary_data,
        companions=companion_files,
        upload_source="connector",
    )
    # Mark as processing (connector conversion pending)
    await file_manager.update_processing_status(str(record.id), "processing", [])

    log.success(
        f"  Connector upload '{primary_name}' + {len(companion_files)} companion(s) "
        f"→ file_id={str(record.file_id)[:8]}.."
    )

    background_tasks.add_task(
        _preprocess_connector,
        owner_id=owner_id,
        file_id=str(record.file_id),
        user_file_id=str(record.id),
        connector=connector,
        sequence_time_mode=sequence_time_mode,
    )

    return JSONResponse(content={
        "status": "ok",
        "files": [{
            "id": str(record.id),
            "file_id": str(record.file_id),
            "original_name": record.original_name,
            "processing_status": "processing",
        }],
    })


async def _upload_dicom_series(
    files: list[UploadFile],
    owner_id: str,
    file_manager: FileManager,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    """Group multiple .dcm files into a single record (one DICOM series)."""
    dcm_files: list[tuple[str, bytes]] = []
    for file in files:
        sanitized = _sanitize_filename(file.filename)
        if not sanitized:
            raise HTTPException(status_code=400, detail=f"Invalid filename: '{file.filename}'")
        data = await file.read()
        dcm_files.append((sanitized, data))

    if not dcm_files:
        raise HTTPException(status_code=400, detail="No DICOM files provided.")

    # First file is primary, rest are companions
    primary_name, primary_data = dcm_files[0]
    companion_data = {name: data for name, data in dcm_files[1:]}

    existing = await file_manager.file_repo.get_by_owner_and_name(owner_id, primary_name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A file named '{primary_name}' already exists.",
        )

    record = await file_manager.upload_to_store(
        owner_id=owner_id,
        filename=primary_name,
        data=primary_data,
        companions=companion_data,
        upload_source="connector",
    )

    log.success(
        f"  DICOM series '{primary_name}' + {len(companion_data)} slice(s) "
        f"→ file_id={str(record.file_id)[:8]}.."
    )

    # Compute stats from the directory (all .dcm files stored together)
    store_dir = str(file_manager.user_file_path(owner_id, str(record.file_id)))
    background_tasks.add_task(
        _compute_file_stats,
        owner_id=owner_id,
        file_id=str(record.file_id),
        filename=primary_name,
    )

    return JSONResponse(content={
        "status": "ok",
        "files": [{
            "id": str(record.id),
            "file_id": str(record.file_id),
            "original_name": record.original_name,
            "processing_status": record.processing_status,
        }],
    })


# ------------------------------------------------------------------
# Upload from URL
# ------------------------------------------------------------------

MAX_URL_DOWNLOAD_SIZE = 500 * 1024 * 1024


class UrlUploadRequest(BaseModel):
    urls: List[dict]


CONTENT_TYPE_TO_EXT = {
    "text/csv": ".csv",
    "application/json": ".json",
    "application/geo+json": ".json",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-excel": ".xls",
    "text/plain": ".csv",
    "text/tab-separated-values": ".tsv",
}


def _ensure_extension(filename: str, resp) -> str:
    """Ensure the filename has a file extension, inferring from Content-Type if missing."""
    _, ext = os.path.splitext(filename)
    if ext:
        return filename
    content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
    inferred = CONTENT_TYPE_TO_EXT.get(content_type)
    if inferred:
        return filename + inferred
    return filename + ".csv"


@router.post("/file/data/upload-url")
async def upload_from_url(
    body: UrlUploadRequest,
    x_owner_id: str = Header(..., alias="X-Owner-Id"),
    file_manager: FileManager = Depends(get_file_manager),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Download files from URLs and save to user data store."""
    x_owner_id = sanitize_filename(x_owner_id)
    log.info(f"URL UPLOAD owner={x_owner_id[:8]}.. {len(body.urls)} URL(s)")
    if len(body.urls) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 URLs per request.")

    uploaded = []
    errors = []
    for entry in body.urls:
        url = entry.get("url", "").strip()
        label = entry.get("label", "").strip()
        if not url:
            continue
        try:
            resp = await httpx_client.get(url, timeout=60.0)
            resp.raise_for_status()
            if len(resp.content) > MAX_URL_DOWNLOAD_SIZE:
                errors.append({"url": url, "error": "File too large"})
                continue

            filename = None
            if label:
                filename = label
            if not filename:
                cd = resp.headers.get("content-disposition", "")
                if "filename=" in cd:
                    filename = cd.split("filename=")[-1].strip("\"'")
            if not filename:
                path = urlparse(url).path
                filename = unquote(os.path.basename(path)) or "download"

            filename = _sanitize_filename(filename)
            if not filename:
                filename = "download"

            filename = _ensure_extension(filename, resp)

            record = await file_manager.upload_to_store(
                owner_id=x_owner_id,
                filename=filename,
                data=resp.content,
                upload_source="url",
                source_url=url,
            )
            log.success(f"  URL stored '{filename}' ({len(resp.content)} bytes) from {url[:60]}")
            uploaded.append({
                "id": str(record.id),
                "file_id": str(record.file_id),
                "original_name": record.original_name,
            })

            _queue_post_upload_tasks(
                background_tasks, x_owner_id,
                file_id=str(record.file_id),
                user_file_id=str(record.id),
                filenames=filename,
            )
        except httpx.HTTPStatusError as e:
            log.warning(f"  URL failed {url[:60]}: HTTP {e.response.status_code}")
            errors.append({"url": url, "error": f"HTTP {e.response.status_code}"})
        except Exception as e:
            log.warning(f"  URL failed {url[:60]}: {e}")
            errors.append({"url": url, "error": str(e)})

    return JSONResponse(
        content={"status": "ok", "files": uploaded, "errors": errors}
    )


# ------------------------------------------------------------------
# Delete / Rename / Reupload
# ------------------------------------------------------------------


@router.delete("/file/data/{file_id}")
async def delete_user_file(
    file_id: str,
    x_owner_id: str = Header(..., alias="X-Owner-Id"),
    file_manager: FileManager = Depends(get_file_manager),
):
    file_id = sanitize_filename(file_id)
    x_owner_id = sanitize_filename(x_owner_id)
    uf = await file_manager.get_file_by_id(file_id)
    if not uf or str(uf.owner_id) != x_owner_id:
        raise HTTPException(status_code=404, detail="File not found.")

    refs = await file_manager.get_rooms_for_file(file_id)
    affected_room_ids = [str(r.room_id) for r in refs]
    deleted = await file_manager.delete_file(x_owner_id, file_id)
    log.info(f"DELETE '{uf.original_name}' (id={file_id[:8]}..) → rooms_affected={len(refs)}")
    return JSONResponse(content={
        "status": "ok",
        "deleted": deleted,
        "rooms_affected": len(refs),
        "affected_room_ids": affected_room_ids,
        "file_name": uf.display_name or uf.original_name,
    })


class RenameRequest(BaseModel):
    display_name: str


@router.put("/file/data/{file_id}/rename")
async def rename_file(
    file_id: str,
    body: RenameRequest,
    x_owner_id: str = Header(..., alias="X-Owner-Id"),
    file_manager: FileManager = Depends(get_file_manager),
):
    file_id = sanitize_filename(file_id)
    x_owner_id = sanitize_filename(x_owner_id)
    uf = await file_manager.get_file_by_id(file_id)
    if not uf or str(uf.owner_id) != x_owner_id:
        raise HTTPException(status_code=404, detail="File not found.")

    await file_manager.rename_file(file_id, body.display_name)
    log.info(f"RENAME '{uf.original_name}' → '{body.display_name}' (id={file_id[:8]}..)")
    return JSONResponse(content={"status": "ok"})


@router.post("/file/data/{file_id}/reupload")
async def reupload_file(
    file_id: str,
    file: UploadFile = File(...),
    x_owner_id: str = Header(..., alias="X-Owner-Id"),
    file_manager: FileManager = Depends(get_file_manager),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    file_id = sanitize_filename(file_id)
    x_owner_id = sanitize_filename(x_owner_id)
    uf = await file_manager.get_file_by_id(file_id)
    if not uf or str(uf.owner_id) != x_owner_id:
        raise HTTPException(status_code=404, detail="File not found.")

    data = await file.read()
    updated = await file_manager.reupload_file(x_owner_id, file_id, data)
    log.info(f"REUPLOAD '{uf.original_name}' (id={file_id[:8]}..) → {len(data)} bytes")

    ext = os.path.splitext(uf.original_name)[1].lower()

    # For Excel files: reset to "processing" so frontend shows spinner
    # while the AI re-processes. Pass old companion names as hints so the
    # LLM tries to reuse the same table labels for compatibility.
    old_companions = _parse_companions(uf.companion_files) if ext in EXCEL_EXTENSIONS else None
    if ext in EXCEL_EXTENSIONS:
        await file_manager.update_processing_status(str(uf.id), "processing", [])

    _queue_post_upload_tasks(
        background_tasks, x_owner_id,
        file_id=str(uf.file_id),
        user_file_id=str(uf.id),
        filenames=uf.original_name,
        previous_companions=old_companions,
    )

    return JSONResponse(content={
        "status": "ok",
        "size_bytes": updated.size_bytes,
        "processing_status": "processing" if ext in EXCEL_EXTENSIONS else updated.processing_status,
    })


@router.post("/file/data/{file_id}/refetch")
async def refetch_url_file(
    file_id: str,
    x_owner_id: str = Header(..., alias="X-Owner-Id"),
    file_manager: FileManager = Depends(get_file_manager),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Re-download a URL-sourced file from its original URL."""
    file_id = sanitize_filename(file_id)
    x_owner_id = sanitize_filename(x_owner_id)
    uf = await file_manager.get_file_by_id(file_id)
    if not uf or str(uf.owner_id) != x_owner_id:
        raise HTTPException(status_code=404, detail="File not found.")
    if uf.upload_source != "url" or not uf.source_url:
        raise HTTPException(status_code=400, detail="File is not URL-sourced.")

    try:
        resp = await httpx_client.get(uf.source_url, timeout=60.0)
        resp.raise_for_status()
        if len(resp.content) > MAX_URL_DOWNLOAD_SIZE:
            raise HTTPException(status_code=413, detail="Remote file too large.")
        data = resp.content
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Remote server returned HTTP {e.response.status_code}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch URL: {e}")

    updated = await file_manager.reupload_file(x_owner_id, file_id, data)
    log.info(f"REFETCH '{uf.original_name}' (id={file_id[:8]}..) → {len(data)} bytes from {uf.source_url[:60]}")

    ext = os.path.splitext(uf.original_name)[1].lower()
    old_companions = _parse_companions(uf.companion_files) if ext in EXCEL_EXTENSIONS else None
    if ext in EXCEL_EXTENSIONS:
        await file_manager.update_processing_status(str(uf.id), "processing", [])

    _queue_post_upload_tasks(
        background_tasks, x_owner_id,
        file_id=str(uf.file_id),
        user_file_id=str(uf.id),
        filenames=uf.original_name,
        previous_companions=old_companions,
    )

    return JSONResponse(content={
        "status": "ok",
        "size_bytes": updated.size_bytes,
        "processing_status": "processing" if ext in EXCEL_EXTENSIONS else updated.processing_status,
    })


# ------------------------------------------------------------------
# File usage
# ------------------------------------------------------------------


@router.get("/file/data/{file_id}/usage")
async def file_usage(
    file_id: str,
    x_owner_id: str = Header(..., alias="X-Owner-Id"),
    file_manager: FileManager = Depends(get_file_manager),
):
    file_id = sanitize_filename(file_id)
    x_owner_id = sanitize_filename(x_owner_id)
    uf = await file_manager.get_file_by_id(file_id)
    if not uf or str(uf.owner_id) != x_owner_id:
        raise HTTPException(status_code=404, detail="File not found.")

    refs = await file_manager.get_rooms_for_file(file_id)
    return JSONResponse(content={"rooms": [str(r.room_id) for r in refs]})


# ------------------------------------------------------------------
# Stale / orphaned file detection
# ------------------------------------------------------------------


def _dir_size(path) -> int:
    """Total size in bytes of all files in a directory."""
    total = 0
    try:
        for entry in os.scandir(path):
            if entry.is_file(follow_symlinks=False):
                total += entry.stat().st_size
    except OSError:
        pass
    return total


@router.get("/file/data/stale/{owner_id}")
async def list_stale_files(
    owner_id: str,
    file_manager: FileManager = Depends(get_file_manager),
):
    """Identify data-store directories not tracked by any DB record.

    Scans {DIVE_PATH}/{owner_id}/data/ for file_uuid directories
    and compares against user_files records. Returns orphaned entries.
    """
    owner_id = sanitize_filename(owner_id)
    data_root = user_file_path(owner_id, "").parent  # {DIVE_PATH}/{owner_id}/data
    if not data_root.exists():
        log.info(f"STALE owner={owner_id[:8]}.. → data dir does not exist")
        return JSONResponse(content={"stale": [], "total_bytes": 0})

    # Collect all file_uuid dirs on disk
    disk_ids = set()
    for entry in os.scandir(data_root):
        if entry.is_dir(follow_symlinks=False):
            disk_ids.add(entry.name)

    # Collect all file_ids from DB
    db_files = await file_manager.get_user_files(owner_id)
    db_ids = {str(f.file_id) for f in db_files}

    # Orphaned = on disk but not in DB
    orphaned_ids = disk_ids - db_ids
    stale = []
    total_bytes = 0
    for fid in sorted(orphaned_ids):
        dir_path = data_root / fid
        files = []
        try:
            files = [e.name for e in os.scandir(dir_path) if e.is_file(follow_symlinks=False)]
        except OSError:
            pass
        size = _dir_size(dir_path)
        total_bytes += size
        stale.append({
            "file_id": fid,
            "path": str(dir_path),
            "files": files,
            "size_bytes": size,
        })

    log.info(f"STALE owner={owner_id[:8]}.. → {len(stale)} orphaned dir(s), {total_bytes} bytes")
    return JSONResponse(content={"stale": stale, "total_bytes": total_bytes})


@router.delete("/file/data/stale/{owner_id}")
async def cleanup_stale_files(
    owner_id: str,
    file_manager: FileManager = Depends(get_file_manager),
):
    """Delete orphaned data-store directories not tracked by any DB record."""
    import shutil

    data_root = user_file_path(owner_id, "").parent
    if not data_root.exists():
        return JSONResponse(content={"deleted": 0, "freed_bytes": 0})

    disk_ids = set()
    for entry in os.scandir(data_root):
        if entry.is_dir(follow_symlinks=False):
            disk_ids.add(entry.name)

    db_files = await file_manager.get_user_files(owner_id)
    db_ids = {str(f.file_id) for f in db_files}

    orphaned_ids = disk_ids - db_ids
    freed = 0
    deleted = 0
    for fid in orphaned_ids:
        dir_path = data_root / fid
        freed += _dir_size(dir_path)
        shutil.rmtree(dir_path, ignore_errors=True)
        deleted += 1

    log.success(f"STALE CLEANUP owner={owner_id[:8]}.. → deleted={deleted}, freed={freed} bytes")
    return JSONResponse(content={"deleted": deleted, "freed_bytes": freed})
