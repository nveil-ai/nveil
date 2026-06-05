# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Union

from license.billing_provider import SubscriptionInfo, billing_provider

from ..models.license import License
from ..models.license_seat import LicenseSeat, LicenseSeatRole
from ..models.license_catalog import LicenseCatalog
from ..repository.license_repository import LicenseRepository
from ..repository.license_seat_repository import LicenseSeatRepository
from ..repository.license_catalog_repository import LicenseCatalogRepository
from .base import BaseService


from ..models.user import User
from ..repository.user_repository import UserRepository

from logger import logger, INFO, ERROR

class LicenseService(BaseService):
    """License service for managing user licenses"""

    @property
    def license_repo(self) -> LicenseRepository:
        """License repository"""
        return self.get_repo(LicenseRepository, License)
    
    @property
    def license_seat_repo(self) -> LicenseSeatRepository:
        """License seat repository"""
        return self.get_repo(LicenseSeatRepository, LicenseSeat)
    
    @property
    def license_catalog_repo(self) -> LicenseCatalogRepository:
        """License catalog repository"""
        return self.get_repo(LicenseCatalogRepository, LicenseCatalog)

    @property
    def user_repo(self) -> UserRepository:
        """User repository"""
        return self.get_repo(UserRepository, User)

    # --- Type checking helpers ---
    def _is_bool(self, value: str) -> bool:
        """Check if a value is a boolean string"""
        return value.lower() in ("true", "false")

    def _is_int(self, value: str) -> bool:
        """Check if a value is an integer string"""
        return value.removeprefix("-").isdigit()

    def _is_float(self, value: str) -> bool:
        """Check if a value is a float string"""
        val_len = len(value)
        if val_len == 0:
            return False
        dot_count = 0
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

    def _cast_value(self, value: str) -> Union[bool, int, float, str]:
        """Cast a string value to its appropriate type"""
        if self._is_bool(value):
            return value.lower() == "true"
        if self._is_int(value):
            return int(value)
        if self._is_float(value):
            return float(value)
        return value

    async def get_feature_value_for_user(
        self, 
        user_id: str, 
        feature: str
    ) -> Optional[Union[bool, int, float, str]]:
        """
        Get a feature value for a user based on their active license.
        
        Args:
            user_id: The user's ID
            feature: The feature name to look up
            
        Returns:
            The feature value cast to its appropriate type (bool, int, float, or str),
            or None if the user has no active license or the feature doesn't exist.
        """
        # Get the user's active license info
        license_info = await self.get_license_info_for_user(user_id)
        
        if not license_info or not license_info.get("is_active"):
            return None
        
        license_name = license_info.get("license_name")
        if not license_name:
            return None
        
        # Get the feature from the catalog
        feature_entry = await self.license_catalog_repo.get_by_license_and_feature(
            license_name, feature
        )
        
        if not feature_entry:
            return None
        
        # Cast and return the value
        return self._cast_value(feature_entry.value)

    async def get_feature_value_for_user_with_default(
        self,
        user_id: str,
        feature: str,
        default: Union[bool, int, float, str]
    ) -> Union[bool, int, float, str]:
        """
        Get a feature value for a user, returning a default if not found.
        
        Args:
            user_id: The user's ID
            feature: The feature name to look up
            default: Default value to return if feature is not found
            
        Returns:
            The feature value cast to its appropriate type, or the default value.
        """
        value = await self.get_feature_value_for_user(user_id, feature)
        return value if value is not None else default

    async def create_license(
        self,
        license_name: str,
        owner_id: str,
        customer_id: str,
        subscription_id: str,
        max_seats: int,
        start_at: datetime,
        end_at: datetime,
        is_active: bool = True
    ) -> License:
        """Create a new license, deactivate previous active licenses for owner"""
        # 1. Désactiver les licences actives précédentes
        previous_licenses = await self.license_repo.get_active_licenses(owner_id)
        for lic in previous_licenses:
            # Don't deactivate if it's the same subscription (we're updating it)
            if lic.subscription_id != subscription_id:
                await self.license_repo.update_by_id(
                    lic.id,
                    is_active=False,
                    expired_at=datetime.now(timezone.utc)
                )
        await self.session.commit()

        # 2. Vérifier si la licence existe déjà pour cet abonnement
        existing = await self.license_repo.get_by_subscription_id(subscription_id)
        if existing:
            # If it exists, update it with the new details
            await self.license_repo.update_by_id(
                existing.id,
                license_name=license_name,
                owner_id=owner_id,
                customer_id=customer_id,
                max_seats=max_seats,
                start_at=start_at,
                end_at=end_at,
                is_active=is_active,
                expired_at=None
            )
            await self.session.commit()
            # Refresh the object to get updated values
            return await self.license_repo.get_by_id(existing.id)

        # 3. Créer la nouvelle licence
        license_obj = await self.license_repo.create(
            license_name=license_name,
            owner_id=owner_id,
            customer_id=customer_id,
            subscription_id=subscription_id,
            max_seats=max_seats,
            start_at=start_at,
            end_at=end_at,
            is_active=is_active
        )
        await self.session.commit()
        return license_obj

    async def get_license_by_id(self, license_id: str) -> Optional[License]:
        """Get license by ID"""
        return await self.license_repo.get_by_id(license_id)

    async def get_licenses_by_owner(self, owner_id: str) -> List[License]:
        """Get all licenses for an owner"""
        return await self.license_repo.get_by_owner_id(owner_id)

    async def get_active_licenses_by_owner(self, owner_id: str) -> List[License]:
        """Get active licenses for an owner"""
        return await self.license_repo.get_active_licenses(owner_id)

    async def get_license_by_subscription(self, subscription_id: str) -> Optional[License]:
        """Get license by external subscription ID."""
        return await self.license_repo.get_by_subscription_id(subscription_id)

    async def activate_license(self, license_id: str) -> bool:
        """Activate a license"""
        result = await self.license_repo.update_by_id(license_id, is_active=True)
        await self.session.commit()
        return result

    async def deactivate_license(self, license_id: str) -> bool:
        """Deactivate a license"""
        result = await self.license_repo.update_by_id(license_id, is_active=False)
        await self.session.commit()
        return result

    async def expire_license(self, license_id: str) -> bool:
        """Expire a license (set expired_at to now)"""
        result = await self.license_repo.update_by_id(
            license_id,
            is_active=False,
            expired_at=datetime.now(timezone.utc)
        )
        await self.session.commit()
        return result

    async def renew_license(self, license_id: str, new_end_at: datetime) -> bool:
        """Renew a license with a new end date"""
        result = await self.license_repo.update_by_id(
            license_id,
            end_at=new_end_at,
            is_active=True,
            expired_at=None
        )
        await self.session.commit()
        return result

    async def update_max_seats(self, license_id: str, max_seats: int) -> bool:
        """Update the maximum number of seats for a license"""
        if max_seats < 1:
            raise ValueError("max_seats must be at least 1")
        result = await self.license_repo.update_by_id(license_id, max_seats=max_seats)
        await self.session.commit()
        return result

    async def has_available_seats(self, license_id: str) -> bool:
        """Check if a license has available seats"""
        license_obj = await self.license_repo.get_by_id(license_id)
        if not license_obj:
            return False
        current_count = len(license_obj.current_seats) if license_obj.current_seats else 0
        return current_count < license_obj.max_seats

    async def get_available_seat_count(self, license_id: str) -> int:
        """Get the number of available seats for a license"""
        license_obj = await self.license_repo.get_by_id(license_id)
        if not license_obj:
            return 0
        current_count = len(license_obj.current_seats) if license_obj.current_seats else 0
        return max(0, license_obj.max_seats - current_count)

    @staticmethod
    async def fetch_external_subscription(email: Optional[str]) -> Optional[SubscriptionInfo]:
        """Fetch a user's active subscription from the billing provider."""
        if not email:
            return None
        return await billing_provider.fetch_subscription(email)

    async def get_license_info_for_user(self, user_id: str) -> dict:
        """Get license information for a given user, prioritizes Pro over Free.

        Convenience wrapper that performs the billing lookup itself. Hot routes
        should call ``fetch_external_subscription`` outside any DB session
        and then call ``get_license_info_for_user_with_sub``.
        """
        user = await self.user_repo.get_by_id(user_id)
        external_sub = await self.fetch_external_subscription(user.email if user else None)
        return await self.get_license_info_for_user_with_sub(user_id, external_sub)

    async def get_license_info_for_user_with_sub(self, user_id: str, external_sub: Optional[SubscriptionInfo]) -> dict:
        """Get license information given a pre-fetched external subscription (or None)."""
        user = await self.user_repo.get_by_id(user_id)
        active_license = None
        license_modified = False  # Track if we made changes
        now_utc = datetime.now(timezone.utc)

        # Expire stale licenses (e.g. finished trial still marked active)
        licenses_to_check = await self.get_active_licenses_by_owner(user_id)
        for lic in licenses_to_check:
            if lic.end_at and lic.end_at <= now_utc:
                await self.expire_license(str(lic.id))
                license_modified = True

        if user and user.email:
            if external_sub:
                existing_license = await self.license_repo.get_by_subscription_id(external_sub["subscription_id"])

                if not existing_license or not existing_license.is_active:
                    active_license = await self.create_license(
                        license_name=external_sub["product_name"],
                        owner_id=user_id,
                        customer_id=external_sub["customer_id"],
                        subscription_id=external_sub["subscription_id"],
                        max_seats=1,
                        start_at=datetime.fromtimestamp(external_sub["current_period_start"]),
                        end_at=datetime.fromtimestamp(external_sub["current_period_end"]),
                        is_active=True
                    )
                    license_modified = True
                    existing_seat = await self.license_seat_repo.get_by_user_and_license(user_id, active_license.id)
                    if not existing_seat:
                        await self.license_seat_repo.create(
                            user_id=user_id,
                            license_id=active_license.id,
                            role=LicenseSeatRole.OWNER
                        )
                        await self.session.commit()
                else:
                    active_license = existing_license
                    sub_end = datetime.fromtimestamp(external_sub["current_period_end"])
                    if existing_license.end_at != sub_end:
                        await self.license_repo.update_by_id(
                            existing_license.id,
                            end_at=sub_end,
                            start_at=datetime.fromtimestamp(external_sub["current_period_start"])
                        )
                        license_modified = True
                    existing_seat = await self.license_seat_repo.get_by_user_and_license(user_id, active_license.id)
                    if not existing_seat:
                        await self.license_seat_repo.create(
                            user_id=user_id,
                            license_id=active_license.id,
                            role=LicenseSeatRole.OWNER
                        )
                        await self.session.commit()
            else:
                license_to_expire = await self.get_active_licenses_by_owner(user_id)
                # Only expire paid licenses, not trial or free ones
                for lic in license_to_expire:
                    if lic.customer_id not in ("trial_tier", "free_tier"):
                        await self.expire_license(str(lic.id))
                        license_modified = True



        # Commit si modifications
        if license_modified:
            await self.session.commit()

        # 1. Fallback/Selection: Retrieve all active licenses for this user
        # If we already found a Pro license via Stripe, we prioritize it.
        # Otherwise, we look at all active seats in the database.
        if not active_license:
            seats = await self.license_seat_repo.get_by_user_id(user_id)
            active_licenses = []
            for seat in seats:
                lic = await self.license_repo.get_by_id(seat.license_id)
                if lic and lic.is_active and (not lic.end_at or lic.end_at > now_utc):
                    active_licenses.append(lic)
            
            if active_licenses:
                # PRIORITIZATION: Sort by name so 'Pro' comes before 'Free' (alphabetical or specific logic)
                # For now, let's explicitly prefer 'Pro'
                active_licenses.sort(key=lambda l: 0 if "Pro" in l.license_name else 1)
                active_license = active_licenses[0]

        # 2. Last Resort: If no active license at all, create default 'Free'
        if not active_license:
            active_license = await self._create_default_free_license(user_id)
            # Assign the user to the new license seat if not already there
            existing_seat = await self.license_seat_repo.get_by_user_and_license(user_id, active_license.id)
            if not existing_seat:
                await self.license_seat_repo.create(
                    user_id=user_id,
                    license_id=active_license.id,
                    role=LicenseSeatRole.OWNER
                )
                await self.session.commit()

        # 3. Get catalog info
        features = await self.license_catalog_repo.get_by_license(active_license.license_name)
        feature_dict = {f.feature: f.value for f in features}

        # 4. Determine trial status
        is_trial = active_license.customer_id == "trial_tier"
        trial_days_remaining = None
        if is_trial and active_license.end_at:
            remaining = (active_license.end_at - datetime.now(timezone.utc)).days
            trial_days_remaining = max(0, remaining)

        return {
            "license_name": active_license.license_name,  # Direct use, no mapping needed
            "is_active": active_license.is_active,
            "max_seats": active_license.max_seats,
            "start_at": active_license.start_at.isoformat() if active_license.start_at else None,
            "end_at": active_license.end_at.isoformat() if active_license.end_at else None,
            "features": feature_dict,
            "is_trial": is_trial,
            "trial_days_remaining": trial_days_remaining,
            "email": user.email if user else None,
        }

    async def _create_trial_license(self, user_id: str, days: int = 14) -> License:
        """Create a 14-day trial Pro license for a new user.
        
        Args:
            user_id: The user's ID
            days: Number of trial days (default 14)
        """
        from datetime import timedelta
        now = datetime.now(timezone.utc)

        # Deactivate any existing free licenses first
        previous_licenses = await self.license_repo.get_active_licenses(user_id)
        for lic in previous_licenses:
            if lic.customer_id == "free_tier":
                await self.license_repo.update_by_id(
                    lic.id, is_active=False, expired_at=now
                )
        await self.session.commit()

        trial_license = await self.license_repo.create(
            license_name="Pro",
            owner_id=user_id,
            customer_id="trial_tier",
            subscription_id=f"trial_{user_id[:8]}",
            max_seats=1,
            start_at=now,
            end_at=now + timedelta(days=days),
            is_active=True
        )

        # Assign seat to owner
        await self.license_seat_repo.create(
            user_id=user_id,
            license_id=trial_license.id,
            role=LicenseSeatRole.OWNER
        )
        await self.session.commit()
        logger().logp(INFO, f"[License] Trial license created for user {user_id[:8]}... ({days} days)")
        return trial_license

    async def _create_default_free_license(self, user_id: str) -> License:
        """Internal helper to create a default free license"""
        # We reuse create_license but with placeholder values for Stripe fields
        from datetime import timedelta
        now = datetime.now(timezone.utc)

        # Check if they already have one but it's just not assigned correctly? 
        # Actually, if active_license was None, we create a new one.

        return await self.license_repo.create(
            license_name="Free",
            owner_id=user_id,
            customer_id="free_tier",
            subscription_id=f"free_{user_id[:8]}",
            max_seats=1,
            start_at=now,
            end_at=now + timedelta(days=3650), # 10 years for free tier
            is_active=True
        )
