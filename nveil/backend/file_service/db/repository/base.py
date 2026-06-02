# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

from typing import Any, Generic, List, Optional, Type, TypeVar

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeMeta

T = TypeVar("T", bound=DeclarativeMeta)


class BaseRepository(Generic[T]):
    def __init__(self, model: Type[T], session: AsyncSession):
        self.model = model
        self.session = session

    async def get_by_id(self, id: str) -> Optional[T]:
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def create(self, instance: Optional[T] = None, **kwargs) -> T:
        if instance is None:
            instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def update_by_id(self, id: str, **kwargs) -> bool:
        result = await self.session.execute(
            update(self.model).where(self.model.id == id).values(**kwargs)
        )
        await self.session.flush()
        return result.rowcount > 0

    async def delete_by_id(self, id: str) -> bool:
        result = await self.session.execute(
            delete(self.model).where(self.model.id == id)
        )
        await self.session.flush()
        return result.rowcount > 0
