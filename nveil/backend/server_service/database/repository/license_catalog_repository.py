# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

from typing import List, Optional

from sqlalchemy import select

from ..models.license_catalog import LicenseCatalog
from .base import BaseRepository


class LicenseCatalogRepository(BaseRepository[LicenseCatalog]):
    """License catalog repository"""
    async def get_by_license(self, license_name: str) -> Optional[List[LicenseCatalog]]:
        """Get all features for a given license"""
        result = await self.session.execute(
            select(LicenseCatalog)
            .where(LicenseCatalog.license == license_name)
        )
        return list(result.scalars().all())

    async def get_by_feature(self, feature: str, value: str) -> Optional[List[LicenseCatalog]]:
        """Get all licenses for a given feature and value"""
        result = await self.session.execute(
            select(LicenseCatalog)
            .where(LicenseCatalog.feature == feature)
            .where(LicenseCatalog.value == value)
        )
        return list(result.scalars().all())

    async def get_by_license_and_feature(self, license_name: str,
                                            feature: str) -> Optional[LicenseCatalog]:
        """Get all licenses for a given feature and value"""
        result = await self.session.execute(
            select(LicenseCatalog)
            .where(LicenseCatalog.license == license_name)
            .where(LicenseCatalog.feature == feature)
        )
        return result.scalar_one_or_none()
