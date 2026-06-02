# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for RoomService — room creation, membership, messaging."""

import pytest
from pathlib import Path

from testing.factories import insert_user, insert_room, insert_room_member

pytestmark = pytest.mark.db


@pytest.fixture
def room_service(db_session, tmp_path):
    """RoomService with injected tmp workspace path."""
    from database.services.room_service import RoomService

    def fake_workspace(owner_id, room_id):
        return tmp_path / str(owner_id) / str(room_id)

    return RoomService(db_session, workspace_path_fn=fake_workspace)


class TestCreateRoom:
    async def test_creates_directory_and_xml(self, room_service, db_session, tmp_path):
        user = await insert_user(db_session, email="room@test.com")
        room = await room_service.create_room(str(user.id))
        assert room is not None
        assert room.owner_id == user.id
        # Check filesystem
        room_path = tmp_path / str(user.id) / str(room.id)
        assert room_path.exists()
        assert (room_path / "choregraph.xml").exists()

    async def test_nonexistent_owner_raises(self, room_service):
        with pytest.raises(Exception):
            await room_service.create_room("nonexistent-user-id")


class TestJoinRoom:
    async def test_success(self, room_service, db_session):
        owner = await insert_user(db_session, email="owner@test.com")
        room = await insert_room(db_session, str(owner.id))
        await insert_room_member(db_session, str(room.id), str(owner.id), "OWNER")
        member_user = await insert_user(db_session, email="joiner@test.com")
        member = await room_service.join_room(str(room.id), str(member_user.id))
        assert member is not None

    async def test_already_member_raises(self, room_service, db_session):
        owner = await insert_user(db_session, email="owner2@test.com")
        room = await insert_room(db_session, str(owner.id))
        await insert_room_member(db_session, str(room.id), str(owner.id), "OWNER")
        with pytest.raises(Exception):
            await room_service.join_room(str(room.id), str(owner.id))


class TestSendMessage:
    async def test_success(self, room_service, db_session):
        owner = await insert_user(db_session, email="msg_owner@test.com")
        room = await insert_room(db_session, str(owner.id))
        await insert_room_member(db_session, str(room.id), str(owner.id), "OWNER")
        msg = await room_service.send_message(
            str(room.id), str(owner.id), "Hello world"
        )
        assert msg is not None
        assert msg.content == "Hello world"


class TestGetUserRooms:
    async def test_returns_rooms(self, room_service, db_session):
        owner = await insert_user(db_session, email="rooms@test.com")
        room = await insert_room(db_session, str(owner.id))
        await insert_room_member(db_session, str(room.id), str(owner.id), "OWNER")
        rooms = await room_service.get_user_rooms(str(owner.id))
        assert len(rooms) >= 1
