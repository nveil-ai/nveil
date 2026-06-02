# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Service layer for dashboard operations (create, export panel, layout, etc.)."""

import json
import shutil
from typing import List, Optional

from shared.service_client import ServiceClient
from shared.workspace import (
    panel_workspace_path as _panel_workspace_path,
    workspace_path as _workspace_path,
)
from utils import get_secret

from ..models.dashboard_panel import DashboardPanel
from ..models.room import Room, RoomMember, RoomMemberRole, RoomType
from ..models.room_data_ref import RoomDataRef
from ..models.user import User
from ..repository.dashboard_panel_repository import DashboardPanelRepository
from ..repository.room_data_ref_repository import RoomDataRefRepository
from ..repository.room_repository import RoomMemberRepository, RoomRepository
from ..repository.user_repository import UserRepository
from .base import BaseService

MAX_PANELS = 10

FILE_HOST = get_secret("FILE_HOST", "localhost")
FILE_PORT = int(get_secret("FILE_PORT", "8200"))

_file_client = ServiceClient(verify=True)


def _file_url(path: str) -> str:
    return f"https://{FILE_HOST}:{FILE_PORT}{path}"


class DashboardService(BaseService):

    def __init__(self, session, workspace_path_fn=None, panel_workspace_path_fn=None, file_client=None):
        super().__init__(session)
        self._workspace_path = workspace_path_fn or _workspace_path
        self._panel_workspace_path = panel_workspace_path_fn or _panel_workspace_path
        self._file_client = file_client or _file_client

    @property
    def room_repo(self) -> RoomRepository:
        return self.get_repo(RoomRepository, Room)

    @property
    def room_member_repo(self) -> RoomMemberRepository:
        return self.get_repo(RoomMemberRepository, RoomMember)

    @property
    def user_repo(self) -> UserRepository:
        return self.get_repo(UserRepository, User)

    @property
    def panel_repo(self) -> DashboardPanelRepository:
        return self.get_repo(DashboardPanelRepository, DashboardPanel)

    @property
    def ref_repo(self) -> RoomDataRefRepository:
        return self.get_repo(RoomDataRefRepository, RoomDataRef)

    # ------------------------------------------------------------------
    # Dashboard lifecycle
    # ------------------------------------------------------------------

    async def create_dashboard(self, owner_id: str, name: str = None) -> Room:
        """Create a new dashboard room with an empty panels/ directory."""
        owner = await self.user_repo.get_by_id(owner_id)
        if not owner:
            raise ValueError(f"User {owner_id} not found")

        room = await self.room_repo.create(owner_id=owner_id, type=RoomType.DASHBOARD, name=name)

        # Physical directory
        ws = self._workspace_path(str(owner_id), str(room.id))
        (ws / "panels").mkdir(parents=True, exist_ok=True)

        # Owner membership
        await self.room_member_repo.create(
            room_id=room.id, user_id=owner_id, role=RoomMemberRole.OWNER,
        )
        await self.session.commit()
        return room

    async def delete_dashboard(self, dashboard_room_id: str):
        """Delete a dashboard: remove all panel workspaces, remove DB records.

        RoomDataRef entries are cascade-deleted via FK on rooms.id.
        """
        dashboard = await self.room_repo.get_by_id(dashboard_room_id)
        if not dashboard or dashboard.type != RoomType.DASHBOARD:
            raise ValueError("Not a dashboard")

        # Delete dashboard workspace directory (before DB cascade)
        dashboard_ws = self._workspace_path(str(dashboard.owner_id), str(dashboard.id))
        if dashboard_ws.exists():
            shutil.rmtree(dashboard_ws, ignore_errors=True)

        # Delete room — CASCADE handles panels, members, room_data_refs
        await self.room_repo.delete_by_id(dashboard_room_id)
        await self.session.commit()

    async def rename_dashboard(self, dashboard_room_id: str, name: str):
        """Rename a dashboard."""
        dashboard = await self.room_repo.get_by_id(dashboard_room_id)
        if not dashboard or dashboard.type != RoomType.DASHBOARD:
            raise ValueError("Not a dashboard")
        await self.room_repo.update_by_id(dashboard.id, name=name)
        await self.session.commit()

    # ------------------------------------------------------------------
    # Panel management
    # ------------------------------------------------------------------

    async def add_panel(
        self,
        dashboard_room_id: str,
        source_room_id: str,
        title: str = "Untitled",
        spec_filename: Optional[str] = None,
        data_source_config: Optional[str] = None,
    ) -> DashboardPanel:
        """Add a panel to a dashboard.

        Delegates all file operations to file_service via the provision-panel
        endpoint. This method handles only business logic: validation, ID
        generation, DB record creation.
        """
        dashboard = await self.room_repo.get_by_id(dashboard_room_id)
        if not dashboard or dashboard.type != RoomType.DASHBOARD:
            raise ValueError("Target room is not a dashboard")

        count = await self.panel_repo.count_panels(dashboard_room_id)
        if count >= MAX_PANELS:
            raise ValueError(f"Dashboard already has {MAX_PANELS} panels (max)")

        source_room = await self.room_repo.get_by_id(source_room_id)
        if not source_room:
            raise ValueError(f"Source room {source_room_id} not found")

        max_idx = await self.panel_repo.get_max_order_index(dashboard_room_id)
        next_idx = max_idx + 1
        panel_id = f"panel_{next_idx + 1}"

        owner_id = str(dashboard.owner_id)
        target_ws = self._panel_workspace_path(owner_id, str(dashboard.id), panel_id)

        old_prefix = f"/{source_room.owner_id}/workspaces/{source_room.id}/"
        new_prefix = f"/{dashboard.owner_id}/workspaces/{dashboard.id}/panels/{panel_id}/"

        # Call file_service to provision the panel workspace
        resp = await self._file_client.post(
            _file_url(f"/file/rooms/{dashboard_room_id}/provision-panel"),
            json={
                "source_room_id": source_room_id,
                "panel_id": panel_id,
                "target_workspace": str(target_ws),
                "spec_filename": spec_filename,
                "old_path_prefix": old_prefix,
                "new_path_prefix": new_prefix,
            },
            headers={"X-Owner-Id": owner_id},
            timeout=60.0,
        )

        if not resp.ok:
            raise ValueError(
                f"Failed to provision panel workspace: {resp.error}"
            )

        # Build data_source_config from response
        if data_source_config is None:
            url_sources = resp.data.get("url_sources", []) if resp.data else []
            data_source_config = json.dumps({"url_sources": url_sources})

        # Create server_service RoomDataRef rows so the files are anchored to
        # the dashboard room and survive deletion of the source room.
        user_file_ids = resp.data.get("user_file_ids", []) if resp.data else []
        for file_id in user_file_ids:
            existing = await self.ref_repo.get_ref(dashboard_room_id, file_id, panel_id=panel_id)
            if not existing:
                await self.ref_repo.create(
                    room_id=dashboard_room_id,
                    user_file_id=file_id,
                    panel_id=panel_id,
                )

        panel = await self.panel_repo.create(
            room_id=dashboard_room_id,
            panel_id=panel_id,
            title=title,
            source_room_id=source_room_id,
            data_source_config=data_source_config,
            order_index=next_idx,
        )
        await self.session.commit()
        return panel

    async def rename_panel(self, dashboard_room_id: str, panel_id: str, title: str):
        """Rename a panel."""
        panel = await self.panel_repo.get_panel(dashboard_room_id, panel_id)
        if not panel:
            raise ValueError("Panel not found")
        panel.title = title
        await self.session.commit()

    async def remove_panel(self, dashboard_room_id: str, panel_id: str) -> bool:
        """Remove a panel: clean up refs via file_service, delete workspace + DB record."""
        dashboard = await self.room_repo.get_by_id(dashboard_room_id)
        if not dashboard:
            raise ValueError("Dashboard not found")

        owner_id = str(dashboard.owner_id)

        # Delete panel RoomDataRef entries via file_service
        await self._file_client.request(
            "DELETE",
            _file_url(f"/file/rooms/{dashboard_room_id}/panels/{panel_id}"),
            headers={"X-Owner-Id": owner_id},
        )

        # Remove the panel workspace directory
        panel_ws = self._panel_workspace_path(owner_id, str(dashboard.id), panel_id)
        if panel_ws.exists():
            shutil.rmtree(panel_ws, ignore_errors=True)

        deleted = await self.panel_repo.delete_panel(dashboard_room_id, panel_id)
        await self.session.commit()
        return deleted

    async def get_panels(self, dashboard_room_id: str) -> List[DashboardPanel]:
        return await self.panel_repo.get_panels_for_room(dashboard_room_id)

    async def update_layout(self, dashboard_room_id: str, layout_json: str):
        """Persist dockview serialized layout to the dashboard workspace."""
        dashboard = await self.room_repo.get_by_id(dashboard_room_id)
        if not dashboard:
            raise ValueError("Dashboard not found")

        dashboard_ws = self._workspace_path(str(dashboard.owner_id), str(dashboard.id))
        layout_path = dashboard_ws / "dashboard_layout.json"
        layout_path.parent.mkdir(parents=True, exist_ok=True)
        layout_path.write_text(layout_json, encoding="utf-8")

    async def get_layout(self, dashboard_room_id: str) -> Optional[str]:
        """Read the saved dockview layout JSON, or None if not saved yet."""
        dashboard = await self.room_repo.get_by_id(dashboard_room_id)
        if not dashboard:
            return None

        layout_path = self._workspace_path(str(dashboard.owner_id), str(dashboard.id)) / "dashboard_layout.json"
        if layout_path.exists():
            return layout_path.read_text(encoding="utf-8")
        return None
