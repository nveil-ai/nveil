# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.sql import func

from ..models.api_key import ApiKey
from .base import BaseRepository


class ApiKeyRepository(BaseRepository[ApiKey]):

    async def get_by_hash(self, key_hash: str) -> Optional[ApiKey]:
        result = await self.session.execute(
            select(self.model).where(
                self.model.key_hash == key_hash,
                self.model.is_active == True,
                self.model.revoked_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_user(self, user_id) -> List[ApiKey]:
        result = await self.session.execute(
            select(self.model)
            .where(
                self.model.user_id == user_id,
                self.model.revoked_at.is_(None),
            )
            .order_by(self.model.created_at.desc())
        )
        return list(result.scalars().all())

    async def increment_requests(self, key_id) -> None:
        await self.session.execute(
            update(self.model)
            .where(self.model.id == key_id)
            .values(
                total_requests=self.model.total_requests + 1,
                last_used_at=func.now(),
            )
        )
        await self.session.flush()

    async def increment_generations(self, key_id) -> None:
        await self.session.execute(
            update(self.model)
            .where(self.model.id == key_id)
            .values(
                total_generations=self.model.total_generations + 1,
                last_used_at=func.now(),
            )
        )
        await self.session.flush()
