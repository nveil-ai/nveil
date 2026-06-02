# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.sql import func

from ..models.room import Room, RoomMember
from .base import BaseRepository

class	RoomRepository(BaseRepository[Room]):
	async def get_by_token(self, room_token: str) -> Optional[Room]:
		result = await self.session.execute(
			select(Room)
			.where(Room.token == room_token)
		)
		return result.scalar_one_or_none()
	
	async def	get_with_members(self, room_id: str) -> Optional[Room]:
		result = await self.session.execute(
			select(Room)
			.options(selectinload(Room.members)
			.selectinload(RoomMember.user))
			.where(Room.id == room_id))
		return result.scalar_one_or_none()

	async def	get_with_members_by_token(self, room_token: str) -> Optional[Room]:
		result = await self.session.execute(
			select(Room)
			.options(selectinload(Room.members)
			.selectinload(RoomMember.user))
			.where(Room.id == room_token))
		return result.scalar_one_or_none()

	async def	get_user_rooms(self, user_id: str) -> List[Room]:
		result = await self.session.execute(
			select(Room)
			.join(RoomMember, Room.id == RoomMember.room_id)
			.where(RoomMember.user_id == user_id)
			.order_by(Room.last_activity.desc())
		)
		return list(result.scalars().all())

	async def get_by_hostname(self, hostname: str) -> Optional[Room]:
		result = await self.session.execute(
			select(Room)
			.where(func.left(Room.host, 22) == hostname[:22])
		)
		return result.scalar_one_or_none()

class	RoomMemberRepository(BaseRepository[RoomMember]):
	async def	get_membership(self, room_id: str, user_id: str) -> Optional[RoomMember]:
		result = await self.session.execute(
			select(RoomMember)
			.where(
				RoomMember.room_id == room_id,
				RoomMember.user_id == user_id
			)
		)
		return result.scalar_one_or_none()

	async def	get_room_members(self, room_id: str) -> List[RoomMember]:
		result = await self.session.execute(
			select(RoomMember)
			.options(joinedload(RoomMember.user))
			.where(RoomMember.room_id == room_id)
		)
		return list(result.scalars().all())

	async def count_room_members(self, room_id: str) -> int:
		result = await self.session.execute(
			select(func.count())
			.select_from(RoomMember)
			.where(RoomMember.room_id == room_id)
		)
		return result.scalar()

	async def delete_by_room_id(self, room_id: str) -> int:
		"""Delete all members for a given room."""
		result = await self.session.execute(
			delete(RoomMember).where(RoomMember.room_id == room_id)
		)
		await self.session.flush()
		return result.rowcount
	