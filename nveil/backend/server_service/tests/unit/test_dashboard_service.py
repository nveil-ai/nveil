# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for DashboardService — dashboard CRUD, panel management, layout."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from testing.factories import insert_user

pytestmark = pytest.mark.db


@pytest.fixture
def dashboard_service(db_session, tmp_path):
    """DashboardService with injected tmp workspace and mock file client."""
    from database.services.dashboard_service import DashboardService

    def fake_workspace(owner_id, room_id):
        p = tmp_path / str(owner_id) / str(room_id)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def fake_panel_workspace(owner_id, room_id, panel_id):
        p = tmp_path / str(owner_id) / str(room_id) / str(panel_id)
        p.mkdir(parents=True, exist_ok=True)
        return p

    mock_file_client = AsyncMock()
    mock_file_client.post = AsyncMock(return_value=MagicMock(ok=True, data={}))
    mock_file_client.request = AsyncMock(return_value=MagicMock(ok=True, data={}))

    return DashboardService(
        db_session,
        workspace_path_fn=fake_workspace,
        panel_workspace_path_fn=fake_panel_workspace,
        file_client=mock_file_client,
    )


class TestCreateDashboard:
    async def test_creates_room_with_dashboard_type(self, dashboard_service, db_session):
        user = await insert_user(db_session, email="dash@test.com")
        dashboard = await dashboard_service.create_dashboard(str(user.id), "My Dashboard")
        assert dashboard is not None
        assert dashboard.name == "My Dashboard"

    async def test_nonexistent_user_raises(self, dashboard_service):
        with pytest.raises(Exception):
            await dashboard_service.create_dashboard("nonexistent-id", "Fail")


class TestRenameDashboard:
    async def test_rename(self, dashboard_service, db_session):
        user = await insert_user(db_session, email="rename_dash@test.com")
        dashboard = await dashboard_service.create_dashboard(str(user.id), "Old Name")
        await dashboard_service.rename_dashboard(str(dashboard.id), "New Name")


class TestDeleteDashboard:
    async def test_deletes(self, dashboard_service, db_session):
        user = await insert_user(db_session, email="del_dash@test.com")
        dashboard = await dashboard_service.create_dashboard(str(user.id), "To Delete")
        await dashboard_service.delete_dashboard(str(dashboard.id))


class TestLayout:
    async def test_update_and_get(self, dashboard_service, db_session):
        user = await insert_user(db_session, email="layout@test.com")
        dashboard = await dashboard_service.create_dashboard(str(user.id), "Layout Test")
        layout = json.dumps({"type": "row", "children": []})
        await dashboard_service.update_layout(str(dashboard.id), layout)
