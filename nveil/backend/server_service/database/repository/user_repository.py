# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

from typing import List, Optional

from sqlalchemy import select

from ..models.user import User
from .base import BaseRepository


class UserRepository(BaseRepository[User]):
	async def	get_by_email(self, email: str) -> Optional[User]:
		result = await self.session.execute(
			select(User)
			.where(User.email == email))
		return result.scalar_one_or_none()

	async def	get_online_users(self, limit: int = 100) -> List[User]:
		result = await self.session.execute(
			select(User)
			.where(User.is_online == True)
			.order_by(User.last_seen.desc())
			.limit(limit)
		)
		return list(result.scalars().all())

	async def	search_by_email(self, query: str, limit: int = 20) -> List[User]:
		result = await self.session.execute(
			select(User)
			.where(User.email
			.ilike(f"%{query}%"))
			.limit(limit))
		return list(result.scalars().all())
