# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

from typing import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..services.dashboard_service import DashboardService
from ..services.file_service import FileService
from ..services.room_service import RoomService
from ..services.token_service import TokenService
from ..services.user_service import UserService
from .database import db
from ..services.license_service import LicenseService
from ..services.license_seat_service import LicenseSeatService
from ..services.license_catalog_service import LicenseCatalogService


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with db.session() as session:
        yield session


def get_user_service(session: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(session)


def get_room_service(session: AsyncSession = Depends(get_db)) -> RoomService:
    return RoomService(session)


def get_token_service(session: AsyncSession = Depends(get_db)) -> TokenService:
    return TokenService(session)

def get_license_service(session: AsyncSession = Depends(get_db)) -> LicenseService:
    return LicenseService(session)

def get_license_seat_service(session: AsyncSession = Depends(get_db)) -> LicenseSeatService:
    return LicenseSeatService(session)

def get_license_catalog_service(session: AsyncSession = Depends(get_db)) -> LicenseCatalogService:
    return LicenseCatalogService(session)


def get_dashboard_service(session: AsyncSession = Depends(get_db)) -> DashboardService:
    return DashboardService(session)


def get_file_service(session: AsyncSession = Depends(get_db)) -> FileService:
    return FileService(session)
