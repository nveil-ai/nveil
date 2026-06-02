# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Shared async database fixtures for backend service tests.

Usage in a service conftest.py:

    import pytest
    from testing.database import create_test_engine, create_test_session, make_db_override

    @pytest.fixture(scope="session")
    async def engine():
        async for eng in create_test_engine():
            yield eng

    @pytest.fixture
    async def db_session(engine):
        async for session in create_test_session(engine):
            yield session
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, AsyncEngine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

# Import Base so create_all picks up all model metadata.
# Each service conftest must also import its own models before calling create_tables.
# IMPORTANT: Import via the same path the models use (database.models.base, not
# server_service.database.models.base) to avoid duplicate module identities.
import os as _os, sys as _sys
_svc_dir = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "server_service"))
if _svc_dir not in _sys.path:
    _sys.path.insert(0, _svc_dir)
from database.models.base import Base

# Import all server_service models so Base.metadata + ORM relationships
# are fully resolved. Required when file_service tests run separately.
import database.models.user  # noqa: F401
import database.models.room  # noqa: F401
import database.models.message  # noqa: F401
import database.models.refresh_token  # noqa: F401
import database.models.license  # noqa: F401
import database.models.license_catalog  # noqa: F401
import database.models.license_seat  # noqa: F401
import database.models.dashboard_panel  # noqa: F401
import database.models.user_file  # noqa: F401
import database.models.room_data_ref  # noqa: F401
import database.models.api_key  # noqa: F401

DEFAULT_TEST_DATABASE_URL = (
    "postgresql+asyncpg://test_user:test_password@localhost:5433/test_nveil"
)


async def create_test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create an async engine connected to the test Postgres.

    Yields the engine, then disposes it on teardown.
    Use as a session-scoped fixture.
    """
    url = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    engine = create_async_engine(url, poolclass=NullPool, echo=False)
    try:
        yield engine
    finally:
        await engine.dispose()


async def create_tables(engine: AsyncEngine) -> None:
    """Create all tables in the test database.

    Call once per session after importing all models.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_tables(engine: AsyncEngine) -> None:
    """Drop all tables in the test database."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def create_test_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Per-test transactional session that rolls back after each test.

    Yields a session bound to a transaction. The transaction is rolled back
    on teardown, so each test starts with a clean slate.
    """
    connection = await engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()


def make_db_override(session: AsyncSession):
    """Create a FastAPI dependency override for get_db().

    Usage:
        app.dependency_overrides[get_db] = make_db_override(db_session)
    """
    async def _override():
        yield session
    return _override
