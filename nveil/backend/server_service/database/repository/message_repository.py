# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import func

from ..models.message import Message
from ..schema.message import MessageResponse
from .base import BaseRepository

class	MessageRepository(BaseRepository[Message]):
	async def count_user_messages_in_room(self, room_id: str, user_id: str) -> int:
		"""Count messages sent by a specific user in a room."""
		result = await self.session.execute(
			select(func.count())
			.select_from(Message)
			.where(Message.room_id == room_id, Message.author_id == user_id)
		)
		return result.scalar() or 0

	async def	get_room_messages(self, room_id: str, limit: int = 50, offset: int = 0) -> List[MessageResponse]:
		result = await self.session.execute(
			select(Message)
			.options(joinedload(Message.author), joinedload(Message.room))
			.where(Message.room_id  == room_id)
			.order_by(Message.created_at.desc())
			.limit(limit)
			.offset(offset)
		)
		messages = result.scalars().all()
		response: List[MessageResponse] = []
		for message in messages:
			response.append(
				MessageResponse(
					id=str(message.id),
					content=message.content,
					room_token=str(message.room.token),
					author_email=message.author.email,
					created_at=message.created_at,
				)
			)
		return response[::-1]

	async def	get_latest_message(self, room_id: str) -> Optional[MessageResponse]:
		result = await self.session.execute(
			select(Message)
			.options(joinedload(Message.author), joinedload(Message.room))
			.where(Message.room_id == room_id)
			.order_by(Message.created_at.desc())
			.limit(1)
		)
		message = result.scalar_one_or_none()
		if message:
			return MessageResponse(
					id=str(message.id),
					content=message.content,
					room_token=str(message.room.token),
					author_email=message.author.email,
					created_at=message.created_at,
				)
		return None

	async def delete_room_messages(self, room_id: str) -> int:
		"""
		Bulk delete all messages for a room (used before deleting the room).
		Returns number of deleted rows.
		"""
		result = await self.session.execute(
			delete(Message).where(Message.room_id == room_id)
		)
		await self.session.flush()
		return result.rowcount

