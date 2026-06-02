# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Repository for DashboardPanel CRUD operations."""

from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.sql import func

from ..models.dashboard_panel import DashboardPanel
from .base import BaseRepository


class DashboardPanelRepository(BaseRepository[DashboardPanel]):

    async def get_max_order_index(self, room_id: str) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.max(DashboardPanel.order_index), -1))
            .where(DashboardPanel.room_id == room_id)
        )
        return result.scalar()

    async def get_panels_for_room(self, room_id: str) -> List[DashboardPanel]:
        result = await self.session.execute(
            select(DashboardPanel)
            .where(DashboardPanel.room_id == room_id)
            .order_by(DashboardPanel.order_index)
        )
        return list(result.scalars().all())

    async def get_panel(self, room_id: str, panel_id: str) -> Optional[DashboardPanel]:
        result = await self.session.execute(
            select(DashboardPanel)
            .where(
                DashboardPanel.room_id == room_id,
                DashboardPanel.panel_id == panel_id,
            )
        )
        return result.scalar_one_or_none()

    async def count_panels(self, room_id: str) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(DashboardPanel)
            .where(DashboardPanel.room_id == room_id)
        )
        return result.scalar() or 0

    async def delete_panel(self, room_id: str, panel_id: str) -> bool:
        result = await self.session.execute(
            delete(DashboardPanel)
            .where(
                DashboardPanel.room_id == room_id,
                DashboardPanel.panel_id == panel_id,
            )
        )
        await self.session.flush()
        return result.rowcount > 0

    async def delete_all_for_room(self, room_id: str) -> int:
        result = await self.session.execute(
            delete(DashboardPanel).where(DashboardPanel.room_id == room_id)
        )
        await self.session.flush()
        return result.rowcount
