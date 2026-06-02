# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

import shutil
from datetime import datetime
from pathlib import Path
from typing import List

from shared.service_client import ServiceClient
from shared.workspace import workspace_path as _workspace_path

from ..models.message import Message
from ..models.room import Room, RoomMember, RoomMemberRole
from ..models.user import User
from ..repository.message_repository import MessageRepository
from ..repository.room_repository import RoomMemberRepository, RoomRepository
from ..repository.user_repository import UserRepository
from .base import BaseService
from utils import get_secret

FILE_HOST = get_secret("FILE_HOST", "localhost")
FILE_PORT = int(get_secret("FILE_PORT", "8200"))

_file_client = ServiceClient(verify=True)


def _file_url(path: str) -> str:
    return f"https://{FILE_HOST}:{FILE_PORT}{path}"


class RoomService(BaseService):
    def __init__(self, session, workspace_path_fn=None, file_client=None):
        super().__init__(session)
        self._workspace_path = workspace_path_fn or _workspace_path
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
    def message_repo(self) -> MessageRepository:
        return self.get_repo(MessageRepository, Message)

    async def create_room(self, owner_id: str) -> Room:
        owner = await self.user_repo.get_by_id(owner_id)
        if not owner:
            raise ValueError(f"User {owner_id} not found")
        room = await self.room_repo.create(owner_id=owner_id)
        
        # Create physical directory for the room
        room_path = self._workspace_path(str(owner_id), str(room.id))
        room_path.mkdir(parents=True, exist_ok=True)

        # Write empty choregraph.xml so the AI workflow always has a valid file
        empty_choregraph = room_path / "choregraph.xml"
        empty_choregraph.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<choregraph><inputs/><pipeline/></choregraph>',
            encoding="utf-8"
        )

        await self.room_member_repo.create(
            room_id=room.id, user_id=owner_id, role=RoomMemberRole.OWNER
        )
        await self.room_repo.session.commit()
        await self.room_member_repo.session.commit()
        return room

    async def join_room(self, room_id: str, user_id: str) -> RoomMember:
        room = await self.room_repo.get_by_id(room_id)
        if not room:
            raise ValueError(f"Room {room_id} not found")
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        existing_member = await self.room_member_repo.get_membership(room_id, user_id)
        if existing_member:
            raise ValueError(f"User already member of the room")
        membership = await self.room_member_repo.create(
            room_id=room_id, user_id=user_id, role=RoomMemberRole.MEMBER
        )
        await self.room_member_repo.session.commit()
        return membership

    async def	leave_room(self, room_id: str, user_id: str) -> bool:
        membership = await self.room_member_repo.get_membership(room_id, user_id)
        if not membership:
            raise ValueError(f"User is not member of this room")
        if membership.role == RoomMemberRole.OWNER:
            member_count = await self.room_member_repo.count_room_members(room_id)
            if member_count == 1:
                room_obj = await self.room_repo.get_by_id(room_id)
                if room_obj:
                    # await stop_viz(room_obj)

                    # Remove file_service refs for this room before deleting it.
                    # Panel refs (panel_id IS NOT NULL) in dashboard rooms are preserved.
                    owner_id = str(room_obj.owner_id)
                    await self._file_client.request(
                        "DELETE",
                        _file_url(f"/file/rooms/{room_id}"),
                        headers={"X-Owner-Id": owner_id},
                        timeout=10.0,
                    )

                    # Delete physical directory of the room
                    room_data_path = self._workspace_path(owner_id, str(room_obj.id))
                    if room_data_path.exists():
                        shutil.rmtree(room_data_path, ignore_errors=True)
                # Redundant with CASCADE — room deletion cascades to messages/members
                # await self.message_repo.delete_room_messages(room_id)
                # await self.room_member_repo.delete_by_id(membership.id)
                # CASCADE handles messages, members, panels, data_refs
                await self.session.delete(room_obj)
                await self.session.commit()
                return True
            else:
                members = await self.room_member_repo.get_room_members(room_id)
                new_owner = next(
                    (m for m in members if m.user_id != user_id),
                    None
                )
                if new_owner:
                    await self.room_member_repo.update_by_id(new_owner.id, role=RoomMemberRole.OWNER)
                    await self.room_repo.update_by_id(room_id, owner_id=new_owner.user_id)
        if membership and membership.role != RoomMemberRole.OWNER:
            await self.room_member_repo.delete_by_id(membership.id)
        await self.room_repo.session.commit()
        return True

    async def send_message(self, room_id: str, author_id: str, content: str) -> Message:
        author = await self.user_repo.get_by_id(author_id)
        membership = await self.room_member_repo.get_membership(room_id, author_id)
        if not membership and author.email != "bot@nveil.bob":
            raise ValueError("User must be a member to send messages")
        message = await self.message_repo.create(
            room_id=room_id, author_id=author_id, content=content
        )
        await self.room_repo.update_by_id(room_id, last_activity=datetime.now())
        await self.message_repo.session.commit()
        await self.room_repo.session.commit()
        return message

    async def get_room_messages(
        self, room_id: str, user_id: str, limit: int = 50, offset: int = 0
    ) -> List[Message]:
        membership = await self.room_member_repo.get_membership(room_id, user_id)
        if not membership:
            raise ValueError("User must be a member to view messages")
        return await self.message_repo.get_room_messages(room_id, limit, offset)

    async def get_user_rooms(self, user_id: str) -> List[Room]:
        return await self.room_repo.get_user_rooms(user_id)

    async def cleanup_empty_rooms(self, user_id: str, except_room_id: str = None) -> int:
        """Delete chat rooms owned by `user_id` that have no messages.

        Skips dashboards and the optional `except_room_id`. Safe to call
        when the user has no in-flight requests against those rooms (e.g.,
        on logout, idle teardown, or as a periodic background sweep) — the
        previous version of this logic ran inline with /server/rooms/create
        and caused races where concurrent /server/room/start calls 404'd
        against a freshly-deleted room.
        """
        from ..models.room import RoomType
        from logger import INFO, logger

        rooms = await self.room_repo.get_user_rooms(user_id)
        deleted = 0
        for room in rooms:
            if except_room_id and str(room.id) == str(except_room_id):
                continue
            if hasattr(room, 'type') and room.type == RoomType.DASHBOARD:
                continue
            latest = await self.message_repo.get_latest_message(str(room.id))
            if latest is not None:
                continue
            try:
                # Delete physical workspace dir
                room_data_path = self._workspace_path(str(room.owner_id), str(room.id))
                if room_data_path.exists():
                    shutil.rmtree(room_data_path, ignore_errors=True)
                # CASCADE handles members, messages, panels, data_refs
                await self.session.delete(room)
                await self.session.commit()
                deleted += 1
                logger().logp(INFO, f"Cleanup: deleted empty room {str(room.id)[:8]} for user {str(user_id)[:8]}")
            except Exception as e:
                await self.session.rollback()
                logger().logp(INFO, f"Cleanup: failed to delete empty room {str(room.id)[:8]}: {e}")
        return deleted
