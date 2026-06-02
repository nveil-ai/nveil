# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Integration tests for room routes — list, create, delete rooms."""

import pytest

from testing.factories import insert_user, insert_room, insert_room_member

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def mock_externals(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "database.services.room_service._workspace_path",
        lambda o, r: tmp_path / str(o) / str(r),
    )


class TestListRooms:
    async def test_empty_list(self, client, override_auth, db_session):
        user = await insert_user(db_session, email="roomlist@test.com")
        override_auth(user)
        resp = await client.get("/server/rooms/list")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestCreateRoom:
    async def test_unauthenticated_401(self, client):
        resp = await client.post("/server/rooms/create")
        assert resp.status_code in (401, 403)
