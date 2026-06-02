# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Centralized workspace path construction and metadata file I/O.

All services share the same DIVE_PATH filesystem layout. This module
removes the ad-hoc path construction scattered across server, AI, and
viz services and replaces it with one source of truth.

New layout (Phase 0):
    {DIVE_PATH}/{owner_id}/workspaces/{room_id}/
        choregraph.xml
        specifications.xml
        metadata.json
        pipeline/          (was .viz_wrapper)
"""

import json
import os
import re
import shutil
from pathlib import Path
from .secrets import get_secret

DIVE_PATH = get_secret("DIVE_PATH", "/root/DIVE")

CURRENT_WORKSPACE_VERSION = 2


def workspace_path(owner_id: str, room_id: str) -> Path:
    """Root workspace for a room's user files."""
    return Path(DIVE_PATH) / owner_id / "workspaces" / room_id


def panel_workspace_path(owner_id: str, dashboard_room_id: str, panel_id: str) -> Path:
    """Workspace for a specific panel within a dashboard room."""
    return workspace_path(owner_id, dashboard_room_id) / "panels" / panel_id


def workspace_root(owner_id: str, room_id: str) -> str:
    """Workspace root (parent of the room directory)."""
    return str(Path(DIVE_PATH) / owner_id / "workspaces" / room_id)


def metadata_path(owner_id: str, room_id: str) -> Path:
    return workspace_path(owner_id, room_id) / "metadata.json"


def specs_xml_path(owner_id: str, room_id: str) -> Path:
    return workspace_path(owner_id, room_id) / "specifications.xml"


def choregraph_xml_path(owner_id: str, room_id: str) -> Path:
    return workspace_path(owner_id, room_id) / "choregraph.xml"


def user_data_path(owner_id: str) -> Path:
    """Root directory for a user's uploaded data files."""
    return Path(DIVE_PATH) / owner_id / "data"


def user_file_path(owner_id: str, file_id: str) -> Path:
    """Directory for a specific user file (by file_id UUID)."""
    return user_data_path(owner_id) / file_id


def temporal_data_path(ws: Path, subdir: str) -> Path:
    """Return the canonical path for a temporal collection subdirectory.

    Temporal input symlinks live in ``pipeline/inputs/`` so they are
    never wiped by ``clean_pipeline_outputs`` (which only cleans
    ``pipeline/data`` and ``pipeline/cache``).

        {workspace}/pipeline/inputs/{subdir}/
    """
    return ws / "pipeline" / "inputs" / subdir


def link_data_file(
    owner_id: str,
    room_id: str,
    file_id: str,
    filenames: list[str],
    subdir: str = "",
) -> list[Path]:
    """Create symlinks in a room workspace pointing to the user data store.

    Args:
        owner_id: Owner UUID string.
        room_id: Room UUID string.
        file_id: File UUID string (directory name in data store).
        filenames: List of filenames (primary + companions) to symlink.
        subdir: Optional subdirectory within the workspace. When set,
            symlinks are created inside ``workspace/{subdir}/`` instead
            of the workspace root. Used for temporal collections.

    Returns:
        List of created symlink paths.
    """
    ws = workspace_path(owner_id, room_id)
    ws.mkdir(parents=True, exist_ok=True)
    if subdir:
        ws = temporal_data_path(ws, subdir)
        ws.mkdir(parents=True, exist_ok=True)
    store_dir = user_file_path(owner_id, file_id)
    if not store_dir.exists():
        raise OSError(f"Data store directory not found: {store_dir}")
    created = []
    for fname in filenames:
        link = ws / fname
        # DICOM series: symlink to the store directory itself (not a file within it)
        if fname.endswith(".dicom"):
            target = store_dir
        else:
            target = store_dir / fname
            if not target.exists():
                continue  # Skip companions that don't exist
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(target)
        created.append(link)
    return created


def unlink_data_file(owner_id: str, room_id: str, filenames: list[str], subdir: str = "") -> None:
    """Remove symlinks from a room workspace."""
    ws = workspace_path(owner_id, room_id)
    if subdir:
        ws = temporal_data_path(ws, subdir)
    for fname in filenames:
        link = ws / fname
        if link.is_symlink():
            link.unlink()
    # Clean up empty subdirectory
    if subdir:
        sub = workspace_path(owner_id, room_id) / subdir
        if sub.is_dir() and not any(sub.iterdir()):
            sub.rmdir()


def retarget_xml_paths(file_path: Path, old_prefix: str, new_prefix: str) -> bool:
    """Replace old_prefix with new_prefix in location attributes of XML/YAML files.

    Works on choregraph.xml (input location attrs), specifications.xml
    (file location attrs), and catalog.yml (filepath values).
    Returns True if any replacements were made.
    """
    if not file_path.exists():
        return False
    try:
        content = file_path.read_text(encoding="utf-8")
        updated = content.replace(old_prefix, new_prefix)
        if updated != content:
            file_path.write_text(updated, encoding="utf-8")
            return True
    except Exception:
        pass
    return False


def read_metadata(owner_id: str, room_id: str, field: str = None) -> dict:
    """Read room metadata JSON. Returns {} if missing.

    If *field* is given, returns ``{field: value}`` (value may be None).
    Otherwise returns the full metadata dict.
    """
    path = metadata_path(owner_id, room_id)
    if not path.exists():
        return {field: None} if field else {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {field: None} if field else {}
    if field:
        return {field: data.get(field)}
    return data


def write_metadata(owner_id: str, room_id: str, updates: dict):
    """Merge *updates* into the existing metadata JSON file."""
    path = metadata_path(owner_id, room_id)
    existing = {}
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = {}
    existing.update(updates)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


# ------------------------------------------------------------------
# Pipeline cleanup
# ------------------------------------------------------------------


def clean_pipeline_outputs(owner_id: str, room_id: str) -> None:
    """Remove cached pipeline data/cache directories."""
    ws = workspace_path(owner_id, room_id)
    for subdir in ("pipeline/data", "pipeline/cache"):
        d = ws / subdir
        if d.exists():
            shutil.rmtree(d)
            d.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------
# Workspace versioning
# ------------------------------------------------------------------


def get_workspace_version(owner_id: str, room_id: str) -> int:
    """Return workspace version (1 for unversioned rooms)."""
    return read_metadata(owner_id, room_id).get("workspace_version", 1)


def stamp_workspace_version(owner_id: str, room_id: str) -> None:
    """Stamp the current workspace version into metadata."""
    write_metadata(owner_id, room_id, {"workspace_version": CURRENT_WORKSPACE_VERSION})


def cleanup_api_workspace(session_id: str, owner_id: str = "anonymous") -> None:
    """Remove a temporary API workspace."""
    ws = workspace_path(owner_id, session_id)
    if ws.exists():
        shutil.rmtree(ws, ignore_errors=True)
