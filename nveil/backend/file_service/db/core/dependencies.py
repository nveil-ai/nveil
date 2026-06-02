# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

from typing import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db.core.database import db


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with db.session() as session:
        yield session


_service_cache = {}


def get_file_manager(session: AsyncSession = Depends(get_db)):
    # Absolute import (relative to file_service/ working directory)
    from services.file_manager import FileManager

    cache_key = f"file_manager_{id(session)}"
    if cache_key not in _service_cache:
        _service_cache[cache_key] = FileManager(session)
    return _service_cache[cache_key]


def cleanup_service_cache():
    _service_cache.clear()
