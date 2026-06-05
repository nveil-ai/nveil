# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..models.license import License
from .base import BaseRepository


class LicenseRepository(BaseRepository[License]):
    """License repository"""

    async def get_by_owner_id(self, owner_id: str) -> List[License]:
        """Get all licenses for a given owner"""
        result = await self.session.execute(
            select(License)
            .where(License.owner_id == owner_id)
        )
        return list(result.scalars().all())

    async def get_by_customer_id(self, customer_id: str) -> List[License]:
        """Get all licenses for a given billing customer."""
        result = await self.session.execute(
            select(License)
            .where(License.customer_id == customer_id)
        )
        return list(result.scalars().all())

    async def get_by_subscription_id(self, subscription_id: str) -> Optional[License]:
        """Get license by external subscription ID.

        Returns the most recent active license if multiple exist (handles duplicates gracefully).
        """
        result = await self.session.execute(
            select(License)
            .where(License.subscription_id == subscription_id)
            .order_by(License.is_active.desc(), License.start_at.desc())
        )
        licenses = list(result.scalars().all())
        if not licenses:
            return None
        # Return the first (most recent active) license
        return licenses[0]

    async def get_active_licenses(self, owner_id: str) -> List[License]:
        """Get all active licenses for a given owner"""
        result = await self.session.execute(
            select(License)
            .where(License.owner_id == owner_id)
            .where(License.is_active == True)
        )
        return list(result.scalars().all())

    async def get_active_license_by_name(self, owner_id: str, 
                                          license_name: str) -> Optional[License]:
        """Get active license by name for a given owner"""
        result = await self.session.execute(
            select(License)
            .where(License.owner_id == owner_id)
            .where(License.license_name == license_name)
            .where(License.is_active == True)
        )
        return result.scalar_one_or_none()
