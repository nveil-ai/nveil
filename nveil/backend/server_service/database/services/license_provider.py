# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

from abc import ABC, abstractmethod
from typing import Optional, Union


class LicenseProvider(ABC):
    """Interface for license management and feature gating.

    Subclass this to integrate your own license/subscription system.
    See plugins/README.md for a full example.
    """

    @abstractmethod
    async def get_license_info(self, user_id: str) -> dict:
        """Return license details for a user.

        Expected keys::

            {
                "license_name": str,
                "is_active": bool,
                "max_seats": int,
                "start_at": Optional[str],   # ISO 8601
                "end_at": Optional[str],      # ISO 8601
                "features": dict[str, Any],   # feature_name -> value
                "is_trial": bool,
                "trial_days_remaining": Optional[int],
                "email": Optional[str],
            }
        """
        ...

    @abstractmethod
    async def check_feature(
        self, user_id: str, feature: str, value: str = "true"
    ) -> bool:
        ...

    @abstractmethod
    async def get_feature_value(
        self, user_id: str, feature: str
    ) -> Optional[Union[bool, int, float, str]]:
        ...

    @abstractmethod
    async def on_user_created(self, user_id: str) -> None:
        ...


class CommunityLicense(LicenseProvider):
    """Community default: all features enabled, no limits."""

    async def get_license_info(self, user_id: str) -> dict:
        return {
            "license_name": "Community",
            "is_active": True,
            "max_seats": 999,
            "start_at": None,
            "end_at": None,
            "features": {},
            "is_trial": False,
            "trial_days_remaining": None,
            "email": None,
        }

    async def check_feature(
        self, user_id: str, feature: str, value: str = "true"
    ) -> bool:
        return True

    async def get_feature_value(
        self, user_id: str, feature: str
    ) -> Optional[Union[bool, int, float, str]]:
        return None

    async def on_user_created(self, user_id: str) -> None:
        pass


try:
    from nveilplugin.licensing import CloudLicenseProvider as _LicenseImpl
except ImportError:
    _LicenseImpl = CommunityLicense

license_provider = _LicenseImpl()
