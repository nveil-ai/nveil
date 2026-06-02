# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

from typing import Optional

from ..models.license_catalog import LicenseCatalog
from ..repository.license_catalog_repository import LicenseCatalogRepository
from .base import BaseService

class	LicenseCatalogService(BaseService):
    """License catalog service"""
    @property
    def	license_catalog_repo(self) -> LicenseCatalogRepository:
        """License catalog repository"""
        return self.get_repo(LicenseCatalogRepository, LicenseCatalog)

    async def create_license_catalog(self, license_name: str, feature: str,
                                            value: str) -> LicenseCatalog:
        """Create a new license catalog entry or update if already exists"""
        existing = await self.license_catalog_repo.get_by_license_and_feature(license_name, feature)
        if existing:
            existing.value = value
            return await self.license_catalog_repo.update(existing)
        return await self.license_catalog_repo.create(LicenseCatalog(license=license_name,
                                                                    feature=feature, value=value))

    async def update_license_catalog(self, license_name: str, feature: str,
                                            value: str) -> Optional[LicenseCatalog]:
        """Update a license catalog entry"""
        existing = await self.license_catalog_repo.get_by_license_and_feature(license_name, feature)
        if existing:
            existing.value = value
            return await self.license_catalog_repo.update(existing)
        return None

    async def delete_license_catalog(self, license_name: str, feature: str) -> bool:
        """Delete a license catalog entry"""
        existing = await self.license_catalog_repo.get_by_license_and_feature(license_name, feature)
        if existing:
            await self.license_catalog_repo.delete(existing)
            return True
        return False

    async def get_license_catalog(self, license_name: str,
                                    feature: str) -> Optional[LicenseCatalog]:
        """Get a license catalog entry"""
        return await self.license_catalog_repo.get_by_license_and_feature(license_name, feature)

    async def is_feature_allowed(self, license_name: str, feature: str, value: str) -> bool:
        """Check if a feature is allowed for a given license"""
        # Names are now 'Free' and 'Pro' directly in catalog
        license_catalog = await self.license_catalog_repo.get_by_license_and_feature(
            license_name, feature
        )
        if not license_catalog:
            return False
        if await self._is_bool(license_catalog.value) and await self._is_bool(value):
            return license_catalog.value == value
        if await self._is_int(license_catalog.value) and (
            await self._is_int(value) or await self._is_float(value)
        ):
            return int(license_catalog.value) >= int(value)
        if await self._is_float(license_catalog.value) and (
            await self._is_int(value) or await self._is_float(value)
        ):
            return float(license_catalog.value) >= float(value)
        return False

    async def _is_bool(self, value: str) -> bool:
        """Check if a feature is allowed for a given license"""
        return value in ("true", "false")

    async def _is_int(self, value: str) -> bool:
        """Check if a license feature value is an integer"""
        return value.removeprefix("-").isdigit()

    async def _is_float(self, value: str) -> bool:
        """Check if a license feature value is a float (or int)"""
        val_len: int = len(value)
        dot_count: int = 0
        for i, char in enumerate(value):
            if i == 0 and char == "-":
                continue
            if char.isdigit():
                continue
            if dot_count == 0 and char == ".":
                is_valid = (1 < i < val_len - 1) if value[0] == "-" else (0 < i < val_len - 1)
                if is_valid:
                    dot_count += 1
                    continue
            return False
        return True
