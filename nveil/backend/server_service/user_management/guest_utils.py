# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Guest utilities for managing guest user data and sample files.
"""
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.service_client import ServiceClient
from logger import ERROR, INFO, WARNING, logger
from shared.workspace import DIVE_PATH, panel_workspace_path, retarget_xml_paths, workspace_path
from utils import get_secret

GUEST_SHARED_WORKSPACE = Path(DIVE_PATH) / "_guest" / "workspaces" / "shared"
GUEST_DATA_SOURCE = Path("/nveil/guest_data/AirbnbGuest")

FILE_HOST = get_secret("FILE_HOST", "localhost")
FILE_PORT = int(get_secret("FILE_PORT", "8200"))

# Extensions that are data files (uploaded to file_service)
DATA_EXTENSIONS = {'.csv', '.sqlite', '.parquet', '.mhd', '.zraw'}

# Module-level cache for the shared dashboard room ID (set at startup, refreshed from DB on miss)
_shared_dashboard_id: Optional[str] = None

_file_client = ServiceClient(verify=True)


def _file_url(path: str) -> str:
    return f"https://{FILE_HOST}:{FILE_PORT}{path}"


def get_guest_chat_history() -> List[Dict[str, Any]]:
    """
    Load the chat history from chat.json in the shared guest workspace.
    The workspace is provisioned by the Docker entrypoint.
    """
    chat_file = GUEST_SHARED_WORKSPACE / "chat.json"
    if chat_file.exists():
        try:
            return json.loads(chat_file.read_text())
        except Exception:
            return []
    return []


def _rebuild_shared_workspace() -> None:
    """Purge and rebuild the shared guest workspace from the source examples.

    Called on every server startup so that template changes (XML, pipeline
    config, data files) are always picked up without a container restart.

    Uses an atomic-swap pattern to avoid a race condition where
    create_guest_workspace() could read an empty shared directory
    during the rebuild (e.g. during uvicorn hot-reload).
    """
    if not GUEST_DATA_SOURCE.exists():
        logger().logp(WARNING, f"Guest data source not found: {GUEST_DATA_SOURCE}")
        return

    parent = GUEST_SHARED_WORKSPACE.parent
    parent.mkdir(parents=True, exist_ok=True)

    # Build into a temp dir on the same filesystem for atomic rename
    tmp_dir = Path(tempfile.mkdtemp(dir=parent, prefix=".shared_tmp_"))
    try:
        for item in GUEST_DATA_SOURCE.iterdir():
            dst = tmp_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dst)
            else:
                shutil.copy2(item, dst)

        # Atomic swap: move old out, move new in
        old_dir = parent / f".shared_old_{os.getpid()}"
        if old_dir.exists():
            shutil.rmtree(old_dir, ignore_errors=True)
        if GUEST_SHARED_WORKSPACE.exists():
            GUEST_SHARED_WORKSPACE.rename(old_dir)
        tmp_dir.rename(GUEST_SHARED_WORKSPACE)

        # Best-effort cleanup of old directory
        if old_dir.exists():
            shutil.rmtree(old_dir, ignore_errors=True)

        logger().logp(INFO, "Shared guest workspace rebuilt from source examples")
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def create_guest_workspace(owner_id: str, room_id: str) -> Path:
    """Create a lightweight per-guest workspace from the shared template.

    Heavy data files (.csv, .sqlite) are symlinked for speed.
    XML files are *copied* so that the viz builder can safely modify them
    (e.g. restore choregraph backups) without corrupting the shared template.
    The pipeline/ directory is copied so pre-built parquet outputs are
    immediately available (avoids re-running the Kedro pipeline per guest).
    """
    SYMLINK_EXTENSIONS = {'.csv', '.sqlite'}
    ws = workspace_path(owner_id, room_id)
    ws.mkdir(parents=True, exist_ok=True)

    if not GUEST_SHARED_WORKSPACE.exists():
        logger().logp(WARNING, f"Shared guest workspace not found: {GUEST_SHARED_WORKSPACE}")
        return ws

    items = list(GUEST_SHARED_WORKSPACE.iterdir())
    if not items:
        # Shared workspace may be mid-rebuild (atomic swap in progress); retry once
        logger().logp(WARNING, "Shared guest workspace empty, retrying in 1s")
        time.sleep(1)
        items = list(GUEST_SHARED_WORKSPACE.iterdir())

    logger().logp(INFO, f"Creating guest workspace: {len(items)} items from shared template → {ws}")

    for item in items:
        dst = ws / item.name
        if item.is_file():
            if dst.exists() or dst.is_symlink():
                dst.unlink()
            if item.suffix.lower() in SYMLINK_EXTENSIONS:
                try:
                    dst.symlink_to(item)
                except OSError:
                    shutil.copy2(item, dst)
            else:
                shutil.copy2(item, dst)
        elif item.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(item, dst)

    # Replace placeholder paths in specifications with actual owner/room values.
    # Choregraph and catalog files keep their shared path
    # (_guest/workspaces/shared/) so all guests read from the single shared
    # data directory instead of per-guest symlinks.
    old_prefix = "/PLACEHOLDER_OWNER/workspaces/PLACEHOLDER_ROOM/"
    new_prefix = f"/{owner_id}/workspaces/{room_id}/"
    for spec_file in ws.glob("specifications*.xml"):
        retarget_xml_paths(spec_file, old_prefix, new_prefix)

    # Verify that essential files were actually copied
    xml_count = len(list(ws.glob("*.xml")))
    if xml_count == 0:
        logger().logp(WARNING, f"Guest workspace {ws} has no XML files after copy — shared workspace may have been empty")

    return ws


def _restore_pipeline_data(ws: Path) -> None:
    """Copy pre-built parquet files from shared template into workspace pipeline/data.

    Called after _register_and_link_guest_data, which triggers clean_pipeline_outputs
    via the file_service link endpoint and wipes the pre-built parquets.
    """
    shared_data = GUEST_SHARED_WORKSPACE / "pipeline" / "data"
    if not shared_data.is_dir():
        return
    target_data = ws / "pipeline" / "data"
    target_data.mkdir(parents=True, exist_ok=True)
    for pq in shared_data.glob("*.parquet"):
        dst = target_data / pq.name
        if not dst.exists():
            shutil.copy2(pq, dst)


# ---------------------------------------------------------------------------
# Guest data registration with file_service
# ---------------------------------------------------------------------------

async def _register_and_link_guest_data(owner_id: str, room_id: str) -> None:
    """Upload guest data files to file_service and link to source room.

    After create_guest_workspace has copied the template, this function:
    1. Finds data files (.csv, etc.) in the workspace
    2. Uploads them to file_service (creates UserFile + data store)
    3. Links them to the source room (creates RoomDataRef entries)

    The link endpoint rebuilds choregraph.xml + specifications.xml (base
    versions), but the enhanced XML files (specificationsEnhanced_*.xml)
    are separate files and remain untouched.
    """
    ws = workspace_path(owner_id, room_id)
    data_files = [
        f for f in ws.iterdir()
        if (f.is_file() or f.is_symlink()) and f.suffix.lower() in DATA_EXTENSIONS
    ]
    if not data_files:
        logger().logp(WARNING, "No guest data files found for file_service registration")
        return

    try:
        file_ids = []
        for df in data_files:
            # Read content (resolves symlinks)
            content = df.resolve().read_bytes()
            resp = await _file_client.request(
                "POST",
                _file_url("/file/data/upload"),
                files=[("files", (df.name, content, "application/octet-stream"))],
                headers={"X-Owner-Id": owner_id},
            )
            if resp.ok:
                result = resp.data if isinstance(resp.data, dict) else {}
                for f in result.get("files", []):
                    file_ids.append(f["id"])
                    logger().info(f"  Guest data uploaded: {df.name} → {f['id'][:8]}..")
            else:
                logger().warning(f"  Guest data upload failed for {df.name}: {resp.error}")

        if file_ids:
            resp = await _file_client.post(
                _file_url(f"/file/rooms/{room_id}/link"),
                json={"file_ids": file_ids},
                headers={"X-Owner-Id": owner_id},
            )
            if resp.ok:
                logger().logp(INFO, f"Guest data linked to source room: {len(file_ids)} file(s)")
            else:
                logger().warning(f"Guest data link failed: {resp.error}")

    except Exception as e:
        logger().logp(WARNING, f"Guest data registration with file_service failed: {e}")
        logger().logp(WARNING, "Dashboard panels may not have data symlinks (file_service unavailable at startup)")


# ---------------------------------------------------------------------------
# Shared guest dashboard (seeded once on startup)
# ---------------------------------------------------------------------------

GUEST_SYSTEM_EMAIL = "_guest_system@nveil.system"
GUEST_PANELS = [
    ("Price Surface", "specificationsEnhanced_20260109_151406.xml"),
    ("Avg Price by Neighbourhood", "specificationsEnhanced_20260109_150048.xml"),
    ("Listings by City", "specificationsEnhanced_20260109_150128.xml"),
    ("Value Score Analysis", "specificationsEnhanced_20260109_151004.xml"),
    ("NYC Price Map", "specificationsEnhanced_20260109_161208.xml"),
]
GUEST_LAYOUT = {
    "version": 2,
    "layouts": {
        "lg": [
            {"i": "panel_1", "x": 0, "y": 0, "w": 12, "h": 5, "minW": 3, "minH": 2},
            {"i": "panel_2", "x": 0, "y": 5, "w": 5,  "h": 4, "minW": 3, "minH": 2},
            {"i": "panel_3", "x": 5, "y": 5, "w": 7,  "h": 4, "minW": 3, "minH": 2},
            {"i": "panel_4", "x": 0, "y": 9, "w": 7,  "h": 5, "minW": 3, "minH": 2},
            {"i": "panel_5", "x": 7, "y": 9, "w": 5,  "h": 5, "minW": 3, "minH": 2},
        ]
    }
}


async def ensure_guest_dashboard(session) -> None:
    """Tear down all guest data and rebuild from scratch. Called on server startup.

    All guest state is tied to the server lifespan: on restart every guest
    session is invalid (containers killed, tokens stale), so we purge
    everything and recreate the shared demo dashboard fresh.

    Guest data files are uploaded to file_service so that RoomDataRef entries
    exist for the source room, enabling provision-panel to create proper
    symlinks in panel workspaces.
    """
    global _shared_dashboard_id

    _rebuild_shared_workspace()

    from sqlalchemy import select as sa_select, delete as sa_delete
    from database.repository.user_repository import UserRepository
    from database.repository.room_repository import RoomRepository, RoomMemberRepository
    from database.models.user import User
    from database.models.room import Room, RoomMember, RoomMemberRole, RoomType
    from database.models.user_file import UserFile
    from database.services.dashboard_service import DashboardService

    user_repo = UserRepository(User, session)
    room_repo = RoomRepository(Room, session)
    dashboard_svc = DashboardService(session)

    # ── 1. Purge ALL guest users (orphaned sessions from previous run) ──
    guests = (await session.execute(
        sa_select(User).where(
            User.is_guest == True,  # noqa: E712
            User.email != GUEST_SYSTEM_EMAIL,
        )
    )).scalars().all()

    for user in guests:
        uid = str(user.id)
        owner_dir = Path(DIVE_PATH) / uid
        if owner_dir.exists():
            shutil.rmtree(owner_dir)
        # CASCADE handles all child records (rooms, messages, tokens, licenses, etc.)
        await session.execute(sa_delete(User).where(User.id == user.id))

    if guests:
        logger().logp(INFO, f"Purged {len(guests)} orphaned guest user(s)")

    # ── 2. Purge system user's old rooms and workspaces ──
    system_user = await user_repo.get_by_email(GUEST_SYSTEM_EMAIL)
    if not system_user:
        system_user = await user_repo.create(
            name="_guest_system",
            email=GUEST_SYSTEM_EMAIL,
            _password=None,
            is_guest=False,
            email_verified=True,
        )
        await session.commit()
        logger().logp(INFO, "Created _guest_system user")
    else:
        # CASCADE handles messages, members, panels, room_data_refs
        await session.execute(sa_delete(Room).where(Room.owner_id == system_user.id))
        # UserFiles aren't cascade-deleted by room deletion (owned by user, not room)
        await session.execute(sa_delete(UserFile).where(UserFile.owner_id == system_user.id))
        # Wipe workspace directory
        system_dir = Path(DIVE_PATH) / str(system_user.id)
        if system_dir.exists():
            shutil.rmtree(system_dir, ignore_errors=True)
        await session.commit()
        logger().logp(INFO, "Purged system user's old rooms and workspaces")

    # ── 3. Create fresh source room with shared workspace data ──
    owner_id = str(system_user.id)
    member_repo = RoomMemberRepository(RoomMember, session)

    source_room = await room_repo.create(owner_id=owner_id, type=RoomType.CHAT)
    await member_repo.create(room_id=source_room.id, user_id=owner_id, role=RoomMemberRole.OWNER)
    await session.commit()

    source_room_id = str(source_room.id)
    create_guest_workspace(owner_id, source_room_id)

    await _register_and_link_guest_data(owner_id, source_room_id)

    # Restore pre-built parquet files from shared template.
    # clean_pipeline_outputs is called by the link endpoint above, which wipes
    # pipeline/data. Copy the parquets back so panels don't need to re-run Kedro.
    _restore_pipeline_data(workspace_path(owner_id, source_room_id))

    # ── 4. Create fresh dashboard with panels ──
    dashboard = await dashboard_svc.create_dashboard(
        owner_id=owner_id, name="Airbnb Insights"
    )

    for panel_title, spec_file in GUEST_PANELS:
        await dashboard_svc.add_panel(
            dashboard_room_id=str(dashboard.id),
            source_room_id=source_room_id,
            title=panel_title,
            spec_filename=spec_file,
        )

    # Symlink pre-built parquet files into each panel workspace so the
    # viz pod can load data without running the pipeline from scratch.
    source_pipeline_data = workspace_path(owner_id, source_room_id) / "pipeline" / "data"
    if source_pipeline_data.is_dir():
        panels = await dashboard_svc.get_panels(str(dashboard.id))
        for panel in panels:
            panel_data = panel_workspace_path(owner_id, str(dashboard.id), panel.panel_id) / "pipeline" / "data"
            panel_data.mkdir(parents=True, exist_ok=True)
            for pq in source_pipeline_data.glob("*.parquet"):
                link = panel_data / pq.name
                if not link.exists():
                    try:
                        link.symlink_to(pq)
                    except OSError:
                        shutil.copy2(pq, link)

    await dashboard_svc.update_layout(str(dashboard.id), json.dumps(GUEST_LAYOUT))
    await session.commit()

    _shared_dashboard_id = str(dashboard.id)
    logger().logp(INFO, f"Shared guest dashboard seeded: {_shared_dashboard_id[:8]} with {len(GUEST_PANELS)} panels")


async def get_shared_dashboard_id(session=None) -> Optional[str]:
    """Return the shared dashboard room ID.

    Uses an in-memory cache set at startup. If the cache is empty or stale
    (e.g. after a pod swap), falls back to a DB lookup so the guest
    dashboard keeps working without a restart.
    """
    global _shared_dashboard_id
    if _shared_dashboard_id is not None:
        return _shared_dashboard_id

    if session is None:
        return None

    from sqlalchemy import select as sa_select
    from database.models.user import User
    from database.models.room import Room, RoomType

    system_user = (await session.execute(
        sa_select(User).where(User.email == GUEST_SYSTEM_EMAIL)
    )).scalar_one_or_none()
    if not system_user:
        return None

    dashboard = (await session.execute(
        sa_select(Room).where(
            Room.owner_id == system_user.id,
            Room.type == RoomType.DASHBOARD,
        )
    )).scalar_one_or_none()
    if dashboard:
        _shared_dashboard_id = str(dashboard.id)

    return _shared_dashboard_id
