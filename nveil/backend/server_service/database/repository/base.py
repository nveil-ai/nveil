# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

from typing import Any, Generic, List, Optional, Type, TypeVar

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeMeta

T = TypeVar('T', bound=DeclarativeMeta)

class	BaseRepository(Generic[T]):
	def	__init__(self, model: Type[T], session: AsyncSession):
		self.model = model
		self.session = session

	async def get_by_id(self, id: str) -> Optional[T]:
		result = await self.session.execute(
			select(self.model).where(self.model.id == id)
		)
		return result.scalar_one_or_none()

	async def get_many(self, limit: int = 100, offset: int = 0,
					filters: Optional[dict[str, Any]] = None,
					order_by: Optional[str] = None) -> List[T]:
		query = select(self.model)
		if filters:
			for key, value in filters.items():
				if hasattr(self.model, key):
					column = getattr(self.model, key)
					if isinstance(value, dict):
						for op, val in value.items():
							if op == "lt": query = query.where(column < val)
							elif op == "lte": query = query.where(column <= val)
							elif op == "gt": query = query.where(column > val)
							elif op == "gte": query = query.where(column >= val)
							elif op == "ne": query = query.where(column != val)
					else:
						query = query.where(column == value)
		if order_by and hasattr(self.model, order_by):
			query = query.order_by(getattr(self.model, order_by).desc())
		query = query.limit(limit).offset(offset)
		result = await self.session.execute(query)
		return list(result.scalars().all())

	async def create(self, instance: Optional[T] = None, **kwargs) -> T:
		if instance is None:
			instance = self.model(**kwargs)
		self.session.add(instance)
		await self.session.flush()
		return instance
	
	async def update_by_id(self, id: str, **kwargs) -> bool:
		result = await self.session.execute(
			update(self.model)
			.where(self.model.id == id)
			.values(**kwargs)
		)
		await self.session.flush()
		return result.rowcount > 0
	
	async def delete_by_id(self, id: str) -> bool:
		result = await self.session.execute(
			delete(self.model).where(self.model.id == id)
		)
		await self.session.flush()
		return result.rowcount > 0

	async def count(self, filters: Optional[dict] = None) -> int:
		query = select(func.count()).select_from(self.model)
		if filters:
			for key, value in filters.items():
				if hasattr(self.model, key):
					query = query.where(getattr(self.model, key) == value)
		result = await self.session.execute(query)
		return result.scalar() is not None

	async def exists(self, **filters) -> bool:
		query = select(1).select_from(self.model).limit(1)
		for key, value in filters.items():
			if hasattr(self.model, key):
				query = query.where(getattr(self.model, key) == value)
		result = await self.session.execute(query)
		return result.scalar() is not None
