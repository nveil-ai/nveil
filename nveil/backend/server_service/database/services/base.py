# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

from typing import Dict, Type

from sqlalchemy.ext.asyncio import AsyncSession

from ..repository.base import BaseRepository


class BaseService:

    def __init__(self, session: AsyncSession):
        self.session = session
        self._repos: Dict[Type, BaseRepository] = {}

    def get_repo(self, repo_class: Type[BaseRepository], model: Type) -> BaseRepository:
        if repo_class not in self._repos:
            self._repos[repo_class] = repo_class(model, self.session)
        return self._repos[repo_class]

    async def commit(self):
        await self.session.commit()

    async def rollback(self):
        await self.session.rollback()

    def __del__(self):
        self._repos.clear()
