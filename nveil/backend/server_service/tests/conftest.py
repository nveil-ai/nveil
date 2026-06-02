# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Fixtures for server_service tests."""

import os
import sys

# Set env vars before model/server imports — they read at import time.
os.environ.setdefault("DATABASE_SCHEMA", "public")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test_user:test_password@localhost:5433/test_nveil")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32B!")  # 36 bytes — avoids PyJWT InsecureKeyLengthWarning
os.environ.setdefault("ALGORITHM", "HS256")

# Ensure service root is importable (mirrors server.py sys.path setup)
_service_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_backend_dir = os.path.abspath(os.path.join(_service_dir, ".."))
_tools_dir = os.path.join(_backend_dir, "tools")
if _service_dir not in sys.path:
    sys.path.insert(0, _service_dir)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)
if _tools_dir not in sys.path:
    sys.path.append(_tools_dir)

import pytest
from httpx import ASGITransport, AsyncClient

from testing.database import create_test_engine, create_tables, drop_tables, create_test_session, make_db_override
from testing.auth import make_auth_headers, TEST_SECRET_KEY, TEST_ALGORITHM

# Import all models so Base.metadata knows about every table
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


@pytest.fixture(scope="session")
async def engine():
    async for eng in create_test_engine():
        yield eng


@pytest.fixture(scope="session")
async def _setup_db(engine):
    """Create all tables once per test session, drop on teardown."""
    await create_tables(engine)
    yield
    await drop_tables(engine)


@pytest.fixture
async def db_session(engine, _setup_db):
    """Per-test transactional session (rolled back after each test)."""
    async for session in create_test_session(engine):
        yield session


@pytest.fixture
def auth_headers():
    """Valid JWT auth headers for test requests."""
    return make_auth_headers()


@pytest.fixture
async def server_app(db_session, monkeypatch):
    """Server FastAPI app with test DB and test secrets — no lifespan side effects."""
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)
    monkeypatch.setenv("ALGORITHM", TEST_ALGORITHM)

    from app_factory import create_app
    from database.core.dependencies import get_db

    app = create_app(lifespan=None)
    app.dependency_overrides[get_db] = make_db_override(db_session)
    # Store db_session on app so integration tests can access it for user lookup
    app.state.db_session = db_session
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def override_auth(server_app):
    """Helper to override get_current_user for a specific user.

    Usage in integration tests:
        def test_something(self, client, override_auth, db_session):
            user = await insert_user(db_session, email="x@test.com")
            override_auth(user)
            resp = await client.get("/server/rooms/list", ...)
    """
    from user_management.authentification import get_current_user

    def _override(user):
        server_app.dependency_overrides[get_current_user] = lambda: user
    return _override


@pytest.fixture
async def client(server_app):
    """Async HTTP test client for server_service."""
    transport = ASGITransport(app=server_app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac
