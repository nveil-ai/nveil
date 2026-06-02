# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Room file management routes: link, unlink, apply, panel provisioning."""

import asyncio
import json
import os
import re
import shutil
from lxml import etree
from collections import defaultdict
from pathlib import Path
from typing import List, Optional

from db.core.dependencies import get_file_manager
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from logger import logger as _logger
from pydantic import BaseModel
from services.file_manager import FileManager, linkable_filenames, temporal_subdir

from choregraph.file_builder import (
    build_choregraph_inputs,
    create_specifications_xml,
)
from shared.workspace import (
    clean_pipeline_outputs,
    get_workspace_version,
    link_data_file,
    retarget_xml_paths,
    stamp_workspace_version,
    temporal_data_path,
    user_file_path,
    workspace_path as _workspace_path,
)

log = _logger()

router = APIRouter()

# Per-room asyncio locks to prevent concurrent modifications
_room_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


class LinkFilesRequest(BaseModel):
    file_ids: List[str]



@router.post("/file/rooms/{room_id}/link")
async def link_files_to_room(
    room_id: str,
    body: LinkFilesRequest,
    x_owner_id: str = Header(..., alias="X-Owner-Id"),
    file_manager: FileManager = Depends(get_file_manager),
):
    """Link files to a room (additive).

    1. Acquire room lock
    2. Link files (symlink + DB via FileManager)
    3. Build/update choregraph.xml (append, preserve IDs)
    4. Create specifications.xml if needed
    5. Clean pipeline outputs
    6. Stamp workspace version if not stamped
    7. Trigger viz reload
    8. Release room lock
    """
    owner_id = x_owner_id
    log.info(f"LINK room={room_id[:8]}.. ← {len(body.file_ids)} file(s)")

    async with _room_locks[room_id]:
        ws = _workspace_path(owner_id, room_id)
        ws.mkdir(parents=True, exist_ok=True)

        linked = []
        new_file_paths = []
        errors = []

        for fid in body.file_ids:
            try:
                ref = await file_manager.link_to_room(owner_id, room_id, fid)
                linked.append(str(ref.id))
                uf = await file_manager.get_file_by_id(fid)
                if uf:
                    log.info(f"  Linked '{uf.original_name}' to room {room_id[:8]}..")
                    for fname in linkable_filenames(uf):
                        p = ws / fname
                        if p.exists() or p.is_symlink():
                            new_file_paths.append(str(p))
            except ValueError as e:
                errors.append({"file_id": fid, "error": str(e)})
            except Exception as e:
                log.error(f"Error linking file {fid[:8]}.. to room {room_id[:8]}..: {e}")
                errors.append({"file_id": fid, "error": str(e)})

        if new_file_paths:
            # Rebuild choregraph.xml from all linked files.
            all_file_paths = []
            all_linked_files = {}
            refs = await file_manager.get_files_for_room(room_id)
            for ref in refs:
                uf = await file_manager.get_file_by_id(str(ref.user_file_id))
                if uf:
                    all_linked_files[str(uf.file_id)] = uf
                    subdir = temporal_subdir(uf) if uf.collection_time_mode else ""
                    base = temporal_data_path(ws, subdir) if subdir else ws
                    for fname in linkable_filenames(uf):
                        p = base / fname
                        if p.exists() or p.is_symlink():
                            all_file_paths.append(str(p))

            clean_pipeline_outputs(owner_id, room_id)

            temporal_info = _build_temporal_info(all_linked_files, ws)
            build_choregraph_inputs(
                workspace_path=str(ws),
                file_paths=all_file_paths,
                existing_xml=None,
                temporal_info=temporal_info,
            )
            log.info(f"  Choregraph rebuilt ({len(all_file_paths)} input(s))")

            create_specifications_xml(str(ws))

            merged = _rebuild_catalogue(ws, owner_id, all_linked_files, temporal_info)
            if merged:
                log.info(f"  Catalogue rebuilt ({merged} dataset(s))")

            if get_workspace_version(owner_id, room_id) < 2:
                stamp_workspace_version(owner_id, room_id)
                log.info(f"  Workspace version stamped (v2)")

    log.success(f"LINK done room={room_id[:8]}.. → linked={len(linked)}, errors={len(errors)}")
    return JSONResponse(
        content={"status": "ok", "linked": linked, "errors": errors}
    )


@router.delete("/file/rooms/{room_id}/unlink/{file_id}")
async def unlink_file_from_room(
    room_id: str,
    file_id: str,
    x_owner_id: str = Header(..., alias="X-Owner-Id"),
    file_manager: FileManager = Depends(get_file_manager),
):
    """Unlink a file from a room.

    1. Acquire room lock
    2. Unlink file (FileManager)
    3. Remove input from choregraph.xml
    4. Clean pipeline outputs
    5. Release room lock
    """
    owner_id = x_owner_id

    async with _room_locks[room_id]:
        uf = await file_manager.get_file_by_id(file_id)
        file_label = uf.original_name if uf else file_id[:8] + ".."

        log.info(f"UNLINK '{file_label}' from room={room_id[:8]}..")

        all_file_paths = []

        try:
            deleted = await file_manager.unlink_from_room(owner_id, room_id, file_id)
        except Exception as e:
            log.error(f"UNLINK failed '{file_label}' from room={room_id[:8]}..: {e}")
            raise HTTPException(status_code=500, detail=str(e))

        if deleted:
            ws = _workspace_path(owner_id, room_id)
            clean_pipeline_outputs(owner_id, room_id)

            # Rebuild choregraph.xml from remaining linked files
            all_file_paths = []
            all_linked_files = {}
            refs = await file_manager.get_files_for_room(room_id)
            for ref in refs:
                ruf = await file_manager.get_file_by_id(str(ref.user_file_id))
                if ruf:
                    all_linked_files[str(ruf.file_id)] = ruf
                    sub = temporal_subdir(ruf) if ruf.collection_time_mode else ""
                    base = temporal_data_path(ws, sub) if sub else ws
                    for fname in linkable_filenames(ruf):
                        p = base / fname
                        if p.exists() or p.is_symlink():
                            all_file_paths.append(str(p))

            if all_file_paths:
                temporal_info = _build_temporal_info(all_linked_files, ws)
                build_choregraph_inputs(
                    workspace_path=str(ws),
                    file_paths=all_file_paths,
                    existing_xml=None,
                    temporal_info=temporal_info,
                )
                log.info(f"  Choregraph rebuilt ({len(all_file_paths)} remaining input(s))")
            else:
                choregraph_xml = ws / "choregraph.xml"
                if choregraph_xml.exists():
                    choregraph_xml.unlink()
                log.info(f"  No inputs remain")

            # Always reset specs — stale channels would reference removed data
            create_specifications_xml(str(ws))

            # Rebuild catalogue with IDs matching choregraph.xml inputs
            if all_linked_files:
                merged = _rebuild_catalogue(ws, owner_id, all_linked_files, temporal_info if all_file_paths else None)
                if merged:
                    log.info(f"  Catalogue rebuilt ({merged} dataset(s))")

    no_sources_remaining = deleted and not all_file_paths
    log.success(f"UNLINK done '{file_label}' → unlinked={deleted} no_sources_remaining={no_sources_remaining}")
    return JSONResponse(content={"status": "ok", "unlinked": deleted, "no_sources_remaining": no_sources_remaining})


# ------------------------------------------------------------------
# Apply (batch link + unlink + metadata merge)
# ------------------------------------------------------------------


class ApplyRequest(BaseModel):
    link_file_ids: List[str] = []
    unlink_file_ids: List[str] = []


def _build_temporal_info(all_linked_files: dict, ws) -> dict:
    """Build temporal_info dict from linked UserFile records.

    Returns a mapping of primary_path → {all_paths, time_mode, time_delta}
    for each temporal group. A single UserFile may produce multiple groups
    (e.g., PhysiCell produces cells + microenvironment CSVs per snapshot).

    Groups are detected by common suffix: files like output00000000_cells.csv
    and output00000001_cells.csv share the suffix '_cells.csv' after removing
    the leading numbered stem.
    """
    import re
    temporal_info = {}
    for fid_str, uf in all_linked_files.items():
        if not uf.collection_time_mode:
            continue
        fnames = linkable_filenames(uf)
        if len(fnames) < 2:
            continue

        subdir = temporal_subdir(uf)
        base = temporal_data_path(ws, subdir)

        # Group files by suffix: strip leading digits/numbering to find common type
        groups: dict[str, list[str]] = {}
        for fn in fnames:
            stem = os.path.splitext(fn)[0]
            ext = os.path.splitext(fn)[1]
            suffix = re.sub(r'^.*?\d+', '', stem) + ext
            if not suffix or suffix == ext:
                suffix = ext
            groups.setdefault(suffix, []).append(fn)

        for suffix, group_fnames in groups.items():
            if len(group_fnames) < 2:
                continue
            paths = sorted(str(base / fn) for fn in group_fnames)
            temporal_info[paths[0]] = {
                "all_paths": paths,
                "time_mode": uf.collection_time_mode,
                "time_delta": uf.collection_time_delta,
            }

    return temporal_info


def _get_choregraph_input_ids(ws) -> dict[str, str]:
    """Parse choregraph.xml and return {filename_stem → input_id}."""
    choregraph_xml = Path(ws) / "choregraph.xml"
    if not choregraph_xml.exists():
        return {}
    try:
        tree = etree.parse(str(choregraph_xml))
        mapping = {}
        for inp in tree.getroot().findall(".//input"):
            location = inp.get("location", "")
            if location:
                stem = os.path.splitext(os.path.basename(location))[0]
                mapping[stem] = inp.get("id")
        return mapping
    except etree.XMLSyntaxError:
        return {}


def _rebuild_catalogue(ws, owner_id: str, all_files: dict, temporal_info: dict | None = None):
    """Rebuild catalogue_stats.json from ALL linked files' precomputed stats.

    Reads ``file_stats.json`` from each file's data store and assigns IDs
    from the just-built ``choregraph.xml`` so catalogue entries match the
    input IDs used by DiveConnector / ASP.

    When ``file_stats.json`` does not exist yet (background task still
    running), stats are computed inline so the catalogue is never empty
    after APPLY.

    Args:
        ws: Workspace path.
        owner_id: Owner ID.
        all_files: Dict of file_id → UserFile for ALL currently-linked files.
    """
    from choregraph.metadata import Metadata, compute_file_stats

    input_ids = _get_choregraph_input_ids(ws)
    entries = {}

    for file_id, uf in all_files.items():
        store_dir = user_file_path(owner_id, file_id)
        ext = os.path.splitext(uf.original_name)[1].lower()
        has_companions = bool(uf.companion_files)

        # For preprocessed files (Excel → parquet, connector XML → CSV),
        # skip the main file — the companions are the real data sources
        # (mirrors linkable_filenames).
        from services.file_manager import _PREPROCESSED_EXTENSIONS
        if not (ext in _PREPROCESSED_EXTENSIONS and has_companions):
            fstats_path = store_dir / "file_stats.json"
            if fstats_path.exists():
                try:
                    fstats = json.loads(fstats_path.read_text(encoding="utf-8"))
                    dataset_name = os.path.splitext(uf.original_name)[0]
                    fstats.setdefault("type", "input")
                    fstats["id"] = input_ids.get(dataset_name)
                    entries[dataset_name] = fstats
                except Exception:
                    pass
            else:
                # Background stats task hasn't finished yet — compute inline
                # so the catalogue is populated immediately after APPLY.
                workspace_file = ws / uf.original_name
                if workspace_file.exists():
                    try:
                        fstats = compute_file_stats(str(workspace_file))
                        if fstats:
                            # Persist so future rebuilds don't recompute
                            fstats_path.write_text(
                                json.dumps(fstats, default=str), encoding="utf-8"
                            )
                            dataset_name = os.path.splitext(uf.original_name)[0]
                            fstats.setdefault("type", "input")
                            fstats["id"] = input_ids.get(dataset_name)
                            entries[dataset_name] = fstats
                            log.info(
                                f"  Stats computed inline for '{uf.original_name}' "
                                f"({len(fstats.get('fields', []))} fields)"
                            )
                    except Exception as e:
                        log.warning(f"  Inline stats failed for '{uf.original_name}': {e}")

        # Companion file stats (parquets from Excel, CSVs from connectors)
        if has_companions:
            try:
                companions = json.loads(uf.companion_files) if isinstance(uf.companion_files, str) else uf.companion_files
            except Exception:
                companions = []
            for cf in (companions or []):
                cf_ext = os.path.splitext(cf)[1].lower()
                if cf_ext not in (".parquet", ".csv"):
                    continue
                cf_stem = os.path.splitext(cf)[0]
                cf_stats_path = store_dir / f"{cf_stem}_file_stats.json"
                if cf_stats_path.exists():
                    try:
                        fstats = json.loads(cf_stats_path.read_text(encoding="utf-8"))
                        dataset_name = cf_stem
                        fstats.setdefault("type", "input")
                        fstats["id"] = input_ids.get(dataset_name)
                        entries[dataset_name] = fstats
                    except Exception:
                        pass

    if not entries:
        return 0

    metadata = Metadata(ws)
    merged = metadata.merge_datasets(entries)

    # Add __partition__ field for temporal collections
    if temporal_info:
        for primary_path, info in temporal_info.items():
            n = len(info["all_paths"])
            dataset_name = os.path.splitext(os.path.basename(primary_path))[0]
            label = "time" if info.get("time_mode") else "partition"
            metadata.add_partition_field(dataset_name, n, partition_label=label)

    return merged


@router.post("/file/rooms/{room_id}/apply")
async def apply_file_changes(
    room_id: str,
    body: ApplyRequest,
    x_owner_id: str = Header(..., alias="X-Owner-Id"),
    file_manager: FileManager = Depends(get_file_manager),
):
    """Apply batched file changes to a room.

    Performs all link + unlink operations atomically, updates choregraph.xml,
    merges pre-computed metadata into catalogue_stats.json, and triggers
    viz reload.
    """
    owner_id = x_owner_id
    has_links = len(body.link_file_ids) > 0
    has_unlinks = len(body.unlink_file_ids) > 0
    log.info(
        f"APPLY room={room_id[:8]}.. "
        f"link={len(body.link_file_ids)} unlink={len(body.unlink_file_ids)}"
    )

    async with _room_locks[room_id]:
        ws = _workspace_path(owner_id, room_id)
        ws.mkdir(parents=True, exist_ok=True)

        linked = []
        linked_names = []
        unlinked = []
        unlinked_names = []
        new_file_paths = []
        filenames_to_remove = []
        errors = []
        linked_files = {}  # file_id → UserFile (for metadata merge)

        # 1. Unlink files
        for fid in body.unlink_file_ids:
            try:
                uf = await file_manager.get_file_by_id(fid)
                if uf:
                    filenames_to_remove.extend(linkable_filenames(uf))
                deleted = await file_manager.unlink_from_room(owner_id, room_id, fid)
                if deleted:
                    unlinked.append(fid)
                    if uf:
                        unlinked_names.append(uf.original_name)
                    log.info(f"  Unlinked '{uf.original_name if uf else fid[:8]}' from room")
            except Exception as e:
                log.error(f"  Unlink error {fid[:8]}..: {e}")
                errors.append({"file_id": fid, "error": str(e)})

        # 2. Link files
        for fid in body.link_file_ids:
            try:
                ref = await file_manager.link_to_room(owner_id, room_id, fid)
                linked.append(str(ref.id))
                uf = await file_manager.get_file_by_id(fid)
                if uf:
                    linked_names.append(uf.original_name)
                    log.info(f"  Linked '{uf.original_name}' to room")
                    linked_files[str(uf.file_id)] = uf
                    sub = temporal_subdir(uf) if uf.collection_time_mode else ""
                    base = temporal_data_path(ws, sub) if sub else ws
                    for fname in linkable_filenames(uf):
                        p = base / fname
                        if p.exists() or p.is_symlink():
                            new_file_paths.append(str(p))
            except ValueError as e:
                errors.append({"file_id": fid, "error": str(e)})
            except Exception as e:
                log.error(f"  Link error {fid[:8]}..: {e}")
                errors.append({"file_id": fid, "error": str(e)})

        # 3. Rebuild choregraph.xml from scratch using ALL currently-linked files.
        all_file_paths = []
        if new_file_paths or filenames_to_remove:
            all_linked_files = {}
            refs = await file_manager.get_files_for_room(room_id)
            for ref in refs:
                uf = await file_manager.get_file_by_id(str(ref.user_file_id))
                if uf:
                    all_linked_files[str(uf.file_id)] = uf
                    subdir = temporal_subdir(uf) if uf.collection_time_mode else ""
                    base = temporal_data_path(ws, subdir) if subdir else ws
                    for fname in linkable_filenames(uf):
                        p = base / fname
                        if p.exists() or p.is_symlink():
                            all_file_paths.append(str(p))

            clean_pipeline_outputs(owner_id, room_id)

            if all_file_paths:
                temporal_info = _build_temporal_info(all_linked_files, ws)
                build_choregraph_inputs(
                    workspace_path=str(ws),
                    file_paths=all_file_paths,
                    existing_xml=None,
                    temporal_info=temporal_info,
                )
            else:
                # No files remain — remove choregraph
                choregraph_xml = ws / "choregraph.xml"
                if choregraph_xml.exists():
                    choregraph_xml.unlink()

            # Always reset specs — stale channels would reference removed data
            create_specifications_xml(str(ws))

            # Rebuild catalogue from ALL linked files with correct IDs
            if all_linked_files:
                merged = _rebuild_catalogue(ws, owner_id, all_linked_files, temporal_info)
                if merged:
                    log.info(f"  Catalogue rebuilt ({merged} dataset(s))")

            if get_workspace_version(owner_id, room_id) < 2:
                stamp_workspace_version(owner_id, room_id)

    no_sources_remaining = len(unlinked) > 0 and not all_file_paths
    log.success(
        f"APPLY done room={room_id[:8]}.. "
        f"linked={len(linked)} unlinked={len(unlinked)} errors={len(errors)} "
        f"no_sources_remaining={no_sources_remaining}"
    )
    return JSONResponse(content={
        "status": "ok",
        "linked": linked,
        "linked_names": linked_names,
        "unlinked": unlinked,
        "unlinked_names": unlinked_names,
        "errors": errors,
        "no_sources_remaining": no_sources_remaining,
    })


# ------------------------------------------------------------------
# Panel provisioning (dashboard panels)
# ------------------------------------------------------------------


class ProvisionPanelRequest(BaseModel):
    source_room_id: str
    panel_id: str
    target_workspace: str
    spec_filename: Optional[str] = None
    old_path_prefix: str
    new_path_prefix: str


def _resolve_active_pair(
    source_ws: Path, spec_filename: Optional[str]
) -> tuple:
    """Return ``(choregraph_file, spec_file)`` for the active visualization."""
    if spec_filename and "specificationsEnhanced_" in spec_filename:
        match = re.search(r"specificationsEnhanced_(\d{8}_\d{6})\.xml", spec_filename)
        if match:
            timestamp = match.group(1)
            cg_name = f"choregraph_{timestamp}.xml"
            if not (source_ws / cg_name).exists():
                cg_name = "choregraph.xml"
            return cg_name, spec_filename
    return "choregraph.xml", "specifications.xml"


def _extract_url_sources(workspace_path: Path) -> list:
    """Parse choregraph.xml and extract URL-based input sources."""
    cg_xml = workspace_path / "choregraph.xml"
    if not cg_xml.exists():
        return []
    try:
        tree = etree.parse(cg_xml)
        urls = []
        for inp in tree.getroot().findall(".//inputs/input"):
            url = inp.get("url")
            if url:
                urls.append({
                    "input_id": inp.get("id", ""),
                    "url": url,
                    "name": inp.get("name", ""),
                })
        return urls
    except Exception:
        return []


@router.post("/file/rooms/{room_id}/provision-panel")
async def provision_panel(
    room_id: str,
    body: ProvisionPanelRequest,
    x_owner_id: str = Header(..., alias="X-Owner-Id"),
    file_manager: FileManager = Depends(get_file_manager),
):
    """Provision a panel workspace: copy specs, create symlinks, create refs.

    This is the single endpoint that handles all file/path operations for
    dashboard panel creation. Server_service sends business parameters,
    file_service handles everything filesystem-related.
    """
    owner_id = x_owner_id
    panel_id = body.panel_id
    target_ws = Path(body.target_workspace)
    source_ws = _workspace_path(owner_id, body.source_room_id)

    log.info(
        f"PROVISION-PANEL room={room_id[:8]}.. panel={panel_id} "
        f"source={body.source_room_id[:8]}.."
    )

    if not source_ws.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Source workspace does not exist: {source_ws}",
        )

    # 1. Create target workspace
    target_ws.mkdir(parents=True, exist_ok=True)

    # 2. Resolve active spec pair from source workspace
    cg_name, spec_name = _resolve_active_pair(source_ws, body.spec_filename)
    cg_src = source_ws / cg_name
    spec_src = source_ws / spec_name

    # 3. Copy active choregraph.xml + specifications.xml (always as base names)
    if spec_src.exists():
        shutil.copy2(str(spec_src), str(target_ws / "specifications.xml"))
    if cg_src.exists():
        shutil.copy2(str(cg_src), str(target_ws / "choregraph.xml"))

    # 4. Rewrite paths in copied files
    for file_path in [
        target_ws / "choregraph.xml",
        target_ws / "specifications.xml",
    ]:
        retarget_xml_paths(file_path, body.old_path_prefix, body.new_path_prefix)

    # 5. Query source room's RoomDataRef entries (regular links only)
    source_refs = await file_manager.get_files_for_room(body.source_room_id)

    # 6. For each ref, create symlinks + panel RoomDataRef
    refs_created = 0
    provisioned_file_ids: list[str] = []
    for ref in source_refs:
        uf = await file_manager.get_file_by_id(str(ref.user_file_id))
        if not uf:
            continue

        provisioned_file_ids.append(str(ref.user_file_id))
        fnames = linkable_filenames(uf)

        # Create symlinks in target workspace pointing to data store
        store_dir = user_file_path(owner_id, str(uf.file_id))
        for fname in fnames:
            target_file = store_dir / fname
            if not target_file.exists():
                continue
            link = target_ws / fname
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(target_file)

        # Create RoomDataRef with panel_id
        existing = await file_manager.ref_repo.get_ref(
            room_id, str(ref.user_file_id), panel_id=panel_id
        )
        if not existing:
            await file_manager.ref_repo.create(
                room_id=room_id,
                user_file_id=str(ref.user_file_id),
                panel_id=panel_id,
            )
            refs_created += 1

    await file_manager.session.commit()

    # 7. Copy metadata.json if present
    meta = source_ws / "metadata.json"
    if meta.exists():
        shutil.copy2(str(meta), str(target_ws / "metadata.json"))

    # 8. Extract URL sources from copied choregraph.xml
    url_sources = _extract_url_sources(target_ws)

    log.success(
        f"PROVISION-PANEL done room={room_id[:8]}.. panel={panel_id} "
        f"refs={refs_created} urls={len(url_sources)}"
    )
    return JSONResponse(content={
        "status": "ok",
        "refs_created": refs_created,
        "url_sources": url_sources,
        "user_file_ids": provisioned_file_ids,
    })


@router.delete("/file/rooms/{room_id}/panels/{panel_id}")
async def delete_panel_refs(
    room_id: str,
    panel_id: str,
    x_owner_id: str = Header(..., alias="X-Owner-Id"),
    file_manager: FileManager = Depends(get_file_manager),
):
    """Delete all RoomDataRef entries for a specific panel."""
    deleted = await file_manager.ref_repo.delete_refs_for_panel(room_id, panel_id)
    await file_manager.session.commit()
    log.info(f"DELETE PANEL REFS room={room_id[:8]}.. panel={panel_id} → {deleted} ref(s)")
    return JSONResponse(content={"status": "ok", "deleted": deleted})


@router.delete("/file/rooms/{room_id}")
async def delete_room_refs(
    room_id: str,
    x_owner_id: str = Header(..., alias="X-Owner-Id"),
    file_manager: FileManager = Depends(get_file_manager),
):
    """Delete all non-panel RoomDataRef entries for a room. Called when a source room is deleted."""
    deleted = await file_manager.ref_repo.delete_refs_for_room(room_id)
    await file_manager.session.commit()
    log.info(f"DELETE ROOM REFS room={room_id[:8]}.. → {deleted} ref(s)")
    return JSONResponse(content={"status": "ok", "deleted": deleted})
