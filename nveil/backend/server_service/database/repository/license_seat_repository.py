# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

from typing import List, Optional

from sqlalchemy import select

from ..models.license_seat import LicenseSeat, LicenseSeatRole
from .base import BaseRepository


class LicenseSeatRepository(BaseRepository[LicenseSeat]):
    """License seat repository"""

    async def get_by_user_id(self, user_id: str) -> List[LicenseSeat]:
        """Get all license seats for a given user"""
        result = await self.session.execute(
            select(LicenseSeat)
            .where(LicenseSeat.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_by_license_id(self, license_id: str) -> List[LicenseSeat]:
        """Get all seats for a given license"""
        result = await self.session.execute(
            select(LicenseSeat)
            .where(LicenseSeat.license_id == license_id)
        )
        return list(result.scalars().all())

    async def get_by_user_and_license(self, user_id: str, 
                                       license_id: str) -> Optional[LicenseSeat]:
        """Get seat for a user on a specific license"""
        result = await self.session.execute(
            select(LicenseSeat)
            .where(LicenseSeat.user_id == user_id)
            .where(LicenseSeat.license_id == license_id)
        )
        return result.scalar_one_or_none()

    async def get_owners_by_license_id(self, license_id: str) -> List[LicenseSeat]:
        """Get all owner seats for a given license"""
        result = await self.session.execute(
            select(LicenseSeat)
            .where(LicenseSeat.license_id == license_id)
            .where(LicenseSeat.role == LicenseSeatRole.OWNER)
        )
        return list(result.scalars().all())

    async def get_admins_by_license_id(self, license_id: str) -> List[LicenseSeat]:
        """Get all admin seats for a given license"""
        result = await self.session.execute(
            select(LicenseSeat)
            .where(LicenseSeat.license_id == license_id)
            .where(LicenseSeat.role == LicenseSeatRole.ADMIN)
        )
        return list(result.scalars().all())

    async def count_seats_by_license_id(self, license_id: str) -> int:
        """Count the number of seats for a given license"""
        seats = await self.get_by_license_id(license_id)
        return len(seats)
