# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later


from logger import INFO, WARNING, logger

from .database import db
from .model import UserProperties


class StateRepository:
    """Repository for AI-service-specific persistence (user preferences)."""

    async def get_user_tone(self, user_id: str):
        async with db.session() as session:
            obj = await session.get(UserProperties, user_id)
            return obj.tone if obj else ""

    async def set_user_tone(self, user_id: str, tone: str):
        async with db.session() as session:
            obj = await session.get(UserProperties, user_id)
            if obj:
                obj.tone = tone
            else:
                obj = UserProperties(user_id=user_id, tone=tone)
                session.add(obj)
            await session.commit()

    async def get_user_compl_info(self, user_id: str):
        async with db.session() as session:
            obj = await session.get(UserProperties, user_id)
            return obj.compl_info if obj else ""

    async def set_user_compl_info(self, user_id: str, compl_info: str):
        async with db.session() as session:
            obj = await session.get(UserProperties, user_id)
            if obj:
                obj.compl_info = compl_info
            else:
                obj = UserProperties(user_id=user_id, compl_info=compl_info)
                session.add(obj)
            await session.commit()
