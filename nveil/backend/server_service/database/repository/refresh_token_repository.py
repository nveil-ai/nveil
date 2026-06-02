# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import and_, or_, select

from ..models.refresh_token import RefreshToken
from .base import BaseRepository


class RefreshTokenRepository(BaseRepository[RefreshToken]):
	async def find_by_token_hash(self, token_hash: str) -> Optional[RefreshToken]:
		result = await self.session.execute(
			select(RefreshToken)
			.where(RefreshToken.token_hash == token_hash)
		)
		return result.scalar_one_or_none()
	
	async def find_active_by_user(self, user_id: str) -> List[RefreshToken]:
		result = await self.session.execute(
			select(RefreshToken)
			.where(
				and_(
					RefreshToken.user_id == user_id,
					RefreshToken.is_revoked == False,
					RefreshToken.expires_at > datetime.now(timezone.utc).replace(tzinfo=None)
				)
			)
		)
		return list(result.scalars().all())
	
	async def find_by_family(self, token_family_id: str) -> List[RefreshToken]:
		result = await self.session.execute(
			select(RefreshToken)
			.where(RefreshToken.token_family_id == token_family_id)
			.order_by(RefreshToken.created_at.desc())
		)
		return list(result.scalars().all())

	async def revoke_family(self, token_family_id: str) -> int:
		tokens = await self.find_by_family(token_family_id)
		count = 0
		for token in tokens:
			token.is_revoked = True
			count += 1
		await self.session.commit()
		return count
	
	async def revoke_user_tokens(self, user_id: str) -> int:
		tokens = await self.find_active_by_user(user_id)
		count = 0
		for token in tokens:
			token.is_revoked = True
			count += 1
		await self.session.commit()
		return count
	
	async def mark_as_used(self, token: RefreshToken) -> None:
		token.is_used = True
		token.used_at = datetime.now(timezone.utc).replace(tzinfo=None)
		await self.session.commit()

	async def cleanup_expired(self) -> int:
		result = await self.session.execute(
			select(RefreshToken)
			.where(
				or_(
					RefreshToken.expires_at < datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7),
					and_(
						RefreshToken.is_revoked == True,
						RefreshToken.created_at < datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
					)
				)
			)
		)
		tokens = list(result.scalars().all())
		for token in tokens:
			await self.session.delete(token)
		await self.session.commit()
		return len(tokens)
