# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Repository for UserFile CRUD operations."""

from typing import List, Optional

from sqlalchemy import select

from ..models.user_file import UserFile
from .base import BaseRepository


class UserFileRepository(BaseRepository[UserFile]):

    async def get_by_file_id(self, file_id: str) -> Optional[UserFile]:
        result = await self.session.execute(
            select(self.model).where(self.model.file_id == file_id)
        )
        return result.scalar_one_or_none()

    async def get_by_owner(self, owner_id: str) -> List[UserFile]:
        result = await self.session.execute(
            select(self.model)
            .where(self.model.owner_id == owner_id)
            .order_by(self.model.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_owner_and_name(self, owner_id: str, original_name: str) -> Optional[UserFile]:
        result = await self.session.execute(
            select(self.model).where(
                self.model.owner_id == owner_id,
                self.model.original_name == original_name,
            )
        )
        return result.scalar_one_or_none()
