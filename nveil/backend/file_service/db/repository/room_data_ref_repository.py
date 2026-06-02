# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Repository for RoomDataRef CRUD operations."""

from typing import List, Optional

from sqlalchemy import delete, select

from ..models.room_data_ref import RoomDataRef
from .base import BaseRepository


class RoomDataRefRepository(BaseRepository[RoomDataRef]):

    async def get_files_for_room(self, room_id: str) -> List[RoomDataRef]:
        """Get refs for a room (regular links only, panel_id IS NULL)."""
        result = await self.session.execute(
            select(self.model).where(
                self.model.room_id == room_id,
                self.model.panel_id.is_(None),
            )
        )
        return list(result.scalars().all())

    async def get_files_for_panel(
        self, room_id: str, panel_id: str
    ) -> List[RoomDataRef]:
        """Get refs for a specific panel within a dashboard room."""
        result = await self.session.execute(
            select(self.model).where(
                self.model.room_id == room_id,
                self.model.panel_id == panel_id,
            )
        )
        return list(result.scalars().all())

    async def get_rooms_for_file(self, user_file_id: str) -> List[RoomDataRef]:
        result = await self.session.execute(
            select(self.model).where(self.model.user_file_id == user_file_id)
        )
        return list(result.scalars().all())

    async def get_ref(
        self, room_id: str, user_file_id: str, panel_id: Optional[str] = None
    ):
        conditions = [
            self.model.room_id == room_id,
            self.model.user_file_id == user_file_id,
        ]
        if panel_id is None:
            conditions.append(self.model.panel_id.is_(None))
        else:
            conditions.append(self.model.panel_id == panel_id)
        result = await self.session.execute(
            select(self.model).where(*conditions)
        )
        return result.scalar_one_or_none()

    async def delete_ref(
        self, room_id: str, user_file_id: str, panel_id: Optional[str] = None
    ) -> bool:
        conditions = [
            self.model.room_id == room_id,
            self.model.user_file_id == user_file_id,
        ]
        if panel_id is None:
            conditions.append(self.model.panel_id.is_(None))
        else:
            conditions.append(self.model.panel_id == panel_id)
        result = await self.session.execute(
            delete(self.model).where(*conditions)
        )
        await self.session.flush()
        return result.rowcount > 0

    async def delete_refs_for_panel(self, room_id: str, panel_id: str) -> int:
        """Delete all refs for a specific panel."""
        result = await self.session.execute(
            delete(self.model).where(
                self.model.room_id == room_id,
                self.model.panel_id == panel_id,
            )
        )
        await self.session.flush()
        return result.rowcount

    async def delete_refs_for_room(self, room_id: str) -> int:
        """Delete all non-panel refs for a room (panel_id IS NULL). Called on room deletion."""
        result = await self.session.execute(
            delete(self.model).where(
                self.model.room_id == room_id,
                self.model.panel_id.is_(None),
            )
        )
        await self.session.flush()
        return result.rowcount
