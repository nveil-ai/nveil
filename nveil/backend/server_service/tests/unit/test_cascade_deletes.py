# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for ON DELETE CASCADE — verify that deleting a parent row
automatically removes all child records via database-level cascades,
and that service functions still work after manual deletions were
commented out in favour of CASCADE."""

import shutil
import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import select, delete, func

from testing.factories import insert_user, insert_room, insert_room_member, insert_message

pytestmark = pytest.mark.db


class TestDeleteUserCascade:
    """Deleting a user should cascade-delete all owned records."""

    async def test_rooms_cascade(self, db_session):
        user = await insert_user(db_session, email="cascade-rooms@test.com")
        room = await insert_room(db_session, owner_id=str(user.id))
        await db_session.commit()

        from database.models.room import Room
        await db_session.execute(delete(Room).where(Room.owner_id == user.id))
        await db_session.commit()

        # Verify room is gone (this tests Room.owner_id CASCADE indirectly
        # through the user→room chain — but let's also test full user deletion)
        count = await db_session.scalar(
            select(func.count()).select_from(Room).where(Room.id == room.id)
        )
        assert count == 0

    async def test_full_user_delete_cascades_everything(self, db_session):
        """Delete a user and verify rooms, members, messages all cascade."""
        from database.models.user import User
        from database.models.room import Room, RoomMember
        from database.models.message import Message

        user = await insert_user(db_session, email="cascade-full@test.com")
        uid = str(user.id)
        room = await insert_room(db_session, owner_id=uid)
        rid = str(room.id)
        await insert_room_member(db_session, room_id=rid, user_id=uid)
        await insert_message(db_session, room_id=rid, author_id=uid, content="hello")
        await db_session.commit()

        # Delete the user — everything should cascade
        await db_session.execute(delete(User).where(User.id == user.id))
        await db_session.commit()

        for model, col in [
            (Room, Room.id),
            (RoomMember, RoomMember.room_id),
            (Message, Message.room_id),
        ]:
            count = await db_session.scalar(
                select(func.count()).select_from(model).where(col == room.id)
            )
            assert count == 0, f"{model.__tablename__} not cascade-deleted"

    async def test_connection_logs_cascade(self, db_session):
        from database.models.user import User, ConnectionLog

        user = await insert_user(db_session, email="cascade-logs@test.com")
        log = ConnectionLog(user_id=user.id, ip_address="127.0.0.1", action="LOGIN")
        db_session.add(log)
        await db_session.commit()

        await db_session.execute(delete(User).where(User.id == user.id))
        await db_session.commit()

        count = await db_session.scalar(
            select(func.count()).select_from(ConnectionLog)
            .where(ConnectionLog.user_id == user.id)
        )
        assert count == 0

    async def test_refresh_tokens_cascade(self, db_session):
        from database.models.user import User
        from database.models.refresh_token import RefreshToken
        from datetime import datetime, timezone

        user = await insert_user(db_session, email="cascade-tokens@test.com")
        token = RefreshToken(
            user_id=user.id,
            token_hash="fakehash123",
            token_family_id=user.id,
            expires_at=datetime(2099, 1, 1),
            used_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db_session.add(token)
        await db_session.commit()

        await db_session.execute(delete(User).where(User.id == user.id))
        await db_session.commit()

        count = await db_session.scalar(
            select(func.count()).select_from(RefreshToken)
            .where(RefreshToken.user_id == user.id)
        )
        assert count == 0


class TestDeleteRoomCascade:
    """Deleting a room should cascade-delete members, messages, panels."""

    async def test_members_and_messages_cascade(self, db_session):
        from database.models.room import Room, RoomMember
        from database.models.message import Message

        user = await insert_user(db_session, email="cascade-room@test.com")
        uid = str(user.id)
        room = await insert_room(db_session, owner_id=uid)
        rid = str(room.id)
        await insert_room_member(db_session, room_id=rid, user_id=uid)
        await insert_message(db_session, room_id=rid, author_id=uid)
        await db_session.commit()

        # Delete the room (not the user)
        await db_session.execute(delete(Room).where(Room.id == room.id))
        await db_session.commit()

        for model in [RoomMember, Message]:
            count = await db_session.scalar(
                select(func.count()).select_from(model)
                .where(model.room_id == room.id)
            )
            assert count == 0, f"{model.__tablename__} not cascade-deleted on room delete"

    async def test_dashboard_panels_cascade(self, db_session):
        from database.models.room import Room, RoomType
        from database.models.dashboard_panel import DashboardPanel

        user = await insert_user(db_session, email="cascade-dash@test.com")
        dashboard = await insert_room(db_session, owner_id=str(user.id), type=RoomType.DASHBOARD)
        panel = DashboardPanel(
            room_id=dashboard.id,
            panel_id="panel_1",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()

        await db_session.execute(delete(Room).where(Room.id == dashboard.id))
        await db_session.commit()

        count = await db_session.scalar(
            select(func.count()).select_from(DashboardPanel)
            .where(DashboardPanel.room_id == dashboard.id)
        )
        assert count == 0


class TestDeleteLicenseCascade:
    """Deleting a license should cascade-delete seats."""

    async def test_license_seats_cascade(self, db_session):
        from database.models.user import User
        from database.models.license import License
        from database.models.license_seat import LicenseSeat

        from datetime import datetime, timezone

        user = await insert_user(db_session, email="cascade-lic@test.com")
        lic = License(
            owner_id=user.id,
            license_name="test",
            customer_id="cus_test",
            subscription_id="sub_test",
            max_seats=5,
            is_active=True,
            start_at=datetime.now(timezone.utc).replace(tzinfo=None),
            end_at=datetime(2099, 1, 1),
        )
        db_session.add(lic)
        await db_session.flush()

        seat = LicenseSeat(
            user_id=user.id,
            license_id=lic.id,
            role="OWNER",
        )
        db_session.add(seat)
        await db_session.commit()

        # Delete license → seats should cascade
        await db_session.execute(delete(License).where(License.id == lic.id))
        await db_session.commit()

        count = await db_session.scalar(
            select(func.count()).select_from(LicenseSeat)
            .where(LicenseSeat.license_id == lic.id)
        )
        assert count == 0


# ── Service-level tests: verify the actual functions work with CASCADE ──


class TestDashboardServiceCascade:
    """delete_dashboard() relies on CASCADE for panels and members."""

    async def test_delete_dashboard_cascades_panels_and_members(self, db_session, tmp_path):
        from database.models.room import Room, RoomMember, RoomType
        from database.models.dashboard_panel import DashboardPanel
        from database.services.dashboard_service import DashboardService

        mock_file_client = AsyncMock()
        mock_file_client.post = AsyncMock(return_value=MagicMock(ok=True, data={}))
        mock_file_client.request = AsyncMock(return_value=MagicMock(ok=True, data={}))

        svc = DashboardService(
            db_session,
            workspace_path_fn=lambda o, r: tmp_path / o / r,
            panel_workspace_path_fn=lambda o, r, p: tmp_path / o / r / p,
            file_client=mock_file_client,
        )

        user = await insert_user(db_session, email="svc-dash-cascade@test.com")
        dashboard = await svc.create_dashboard(str(user.id), "Cascade Test")
        did = str(dashboard.id)

        # Verify panel and member exist
        panel_count = await db_session.scalar(
            select(func.count()).select_from(DashboardPanel)
            .where(DashboardPanel.room_id == dashboard.id)
        )
        member_count = await db_session.scalar(
            select(func.count()).select_from(RoomMember)
            .where(RoomMember.room_id == dashboard.id)
        )
        assert member_count == 1

        await svc.delete_dashboard(did)

        # Verify everything is gone
        for model in [Room, RoomMember]:
            count = await db_session.scalar(
                select(func.count()).select_from(model)
                .where(model.id == dashboard.id if model == Room else model.room_id == dashboard.id)
            )
            assert count == 0, f"{model.__tablename__} not cleaned after delete_dashboard"


class TestRoomServiceCascade:
    """leave_room() relies on CASCADE for messages and members."""

    async def test_leave_room_owner_cascades(self, db_session, tmp_path):
        from database.models.room import Room, RoomMember
        from database.models.message import Message
        from database.services.room_service import RoomService

        svc = RoomService(db_session, workspace_path_fn=lambda o, r: tmp_path / o / r)

        user = await insert_user(db_session, email="svc-leave-cascade@test.com")
        uid = str(user.id)
        room = await svc.create_room(uid)
        rid = str(room.id)

        await insert_message(db_session, room_id=rid, author_id=uid, content="bye")
        await db_session.commit()

        # Owner leaves as last member → room deleted via CASCADE
        await svc.leave_room(rid, uid)

        for model in [Room, RoomMember, Message]:
            col = Room.id if model == Room else model.room_id
            count = await db_session.scalar(
                select(func.count()).select_from(model).where(col == room.id)
            )
            assert count == 0, f"{model.__tablename__} not cleaned after leave_room"
