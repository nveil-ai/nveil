# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

from typing import List, Optional

from ..models.license import License
from ..models.license_seat import LicenseSeat, LicenseSeatRole
from ..repository.license_repository import LicenseRepository
from ..repository.license_seat_repository import LicenseSeatRepository
from .base import BaseService


class LicenseSeatService(BaseService):
    """License seat service for managing user seats on licenses"""

    @property
    def license_seat_repo(self) -> LicenseSeatRepository:
        """License seat repository"""
        return self.get_repo(LicenseSeatRepository, LicenseSeat)

    @property
    def license_repo(self) -> LicenseRepository:
        """License repository"""
        return self.get_repo(LicenseRepository, License)

    async def assign_seat(
        self,
        user_id: str,
        license_id: str,
        role: LicenseSeatRole = LicenseSeatRole.MEMBER
    ) -> LicenseSeat:
        """Assign a seat to a user on a license"""
        # Check if user already has a seat on this license
        existing = await self.license_seat_repo.get_by_user_and_license(user_id, license_id)
        if existing:
            raise ValueError("User already has a seat on this license")

        # Check if license has available seats
        license_obj = await self.license_repo.get_by_id(license_id)
        if not license_obj:
            raise ValueError("License not found")

        if not license_obj.is_active:
            raise ValueError("License is not active")

        current_count = await self.license_seat_repo.count_seats_by_license_id(license_id)
        if current_count >= license_obj.max_seats:
            raise ValueError("No available seats on this license")

        seat = await self.license_seat_repo.create(
            user_id=user_id,
            license_id=license_id,
            role=role
        )
        await self.session.commit()
        return seat

    async def remove_seat(self, user_id: str, license_id: str) -> bool:
        """Remove a user's seat from a license"""
        seat = await self.license_seat_repo.get_by_user_and_license(user_id, license_id)
        if not seat:
            return False

        result = await self.license_seat_repo.delete_by_id(seat.id)
        await self.session.commit()
        return result

    async def change_role(
        self,
        user_id: str,
        license_id: str,
        new_role: LicenseSeatRole
    ) -> bool:
        """Change a user's role on a license"""
        seat = await self.license_seat_repo.get_by_user_and_license(user_id, license_id)
        if not seat:
            return False

        result = await self.license_seat_repo.update_by_id(seat.id, role=new_role)
        await self.session.commit()
        return result

    async def get_user_seats(self, user_id: str) -> List[LicenseSeat]:
        """Get all seats for a user"""
        return await self.license_seat_repo.get_by_user_id(user_id)

    async def get_license_seats(self, license_id: str) -> List[LicenseSeat]:
        """Get all seats for a license"""
        return await self.license_seat_repo.get_by_license_id(license_id)

    async def get_user_seat_on_license(
        self,
        user_id: str,
        license_id: str
    ) -> Optional[LicenseSeat]:
        """Get a user's seat on a specific license"""
        return await self.license_seat_repo.get_by_user_and_license(user_id, license_id)

    async def is_user_on_license(self, user_id: str, license_id: str) -> bool:
        """Check if a user has a seat on a license"""
        seat = await self.license_seat_repo.get_by_user_and_license(user_id, license_id)
        return seat is not None

    async def is_user_owner_or_admin(self, user_id: str, license_id: str) -> bool:
        """Check if a user is an owner or admin on a license"""
        seat = await self.license_seat_repo.get_by_user_and_license(user_id, license_id)
        if not seat:
            return False
        return seat.role in (LicenseSeatRole.OWNER, LicenseSeatRole.ADMIN)

    async def get_license_owners(self, license_id: str) -> List[LicenseSeat]:
        """Get all owners for a license"""
        return await self.license_seat_repo.get_owners_by_license_id(license_id)

    async def get_license_admins(self, license_id: str) -> List[LicenseSeat]:
        """Get all admins for a license"""
        return await self.license_seat_repo.get_admins_by_license_id(license_id)

    async def transfer_ownership(
        self,
        license_id: str,
        from_user_id: str,
        to_user_id: str
    ) -> bool:
        """Transfer ownership of a license from one user to another"""
        from_seat = await self.license_seat_repo.get_by_user_and_license(
            from_user_id, license_id
        )
        if not from_seat or from_seat.role != LicenseSeatRole.OWNER:
            raise ValueError("Current user is not the owner of this license")

        to_seat = await self.license_seat_repo.get_by_user_and_license(
            to_user_id, license_id
        )
        if not to_seat:
            raise ValueError("Target user does not have a seat on this license")

        # Demote current owner to admin
        await self.license_seat_repo.update_by_id(from_seat.id, role=LicenseSeatRole.ADMIN)
        # Promote target user to owner
        await self.license_seat_repo.update_by_id(to_seat.id, role=LicenseSeatRole.OWNER)
        await self.session.commit()
        return True
