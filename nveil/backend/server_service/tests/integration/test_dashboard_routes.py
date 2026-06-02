# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Integration tests for dashboard routes — create, list, delete."""

import pytest

from testing.factories import insert_user

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def mock_externals(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "database.services.dashboard_service._workspace_path",
        lambda o, r: tmp_path / str(o) / str(r),
    )
    monkeypatch.setattr(
        "database.services.room_service._workspace_path",
        lambda o, r: tmp_path / str(o) / str(r),
    )


class TestCreateDashboard:
    async def test_success(self, client, override_auth, db_session):
        user = await insert_user(db_session, email="dash_create@test.com")
        override_auth(user)
        resp = await client.post(
            "/server/dashboards/create",
            json={"name": "Test Dashboard"},
        )
        assert resp.status_code in (200, 201)

    async def test_list_dashboards(self, client, override_auth, db_session):
        user = await insert_user(db_session, email="dash_list@test.com")
        override_auth(user)
        resp = await client.get("/server/dashboards/list")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
