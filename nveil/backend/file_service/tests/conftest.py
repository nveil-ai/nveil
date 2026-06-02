# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Fixtures for file_service tests."""

import os
import sys

# Set env vars before any model imports
os.environ.setdefault("DATABASE_SCHEMA", "public")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test_user:test_password@localhost:5433/test_nveil")

# Ensure service root is importable
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

# testing.database adds server_service to sys.path and imports all models
# (including UserFile + RoomDataRef which live in both services).
from testing.database import (
    Base,
    create_test_engine,
    create_test_session,
    create_tables,
    drop_tables,
    make_db_override,
)

# testing.database inserts server_service/ at sys.path[0], which shadows
# file_service/routes with server_service/routes.  Re-insert file_service/
# at position 0 so `import routes.data` resolves to file_service/routes/data.py.
if sys.path[0] != _service_dir:
    try:
        sys.path.remove(_service_dir)
    except ValueError:
        pass
    sys.path.insert(0, _service_dir)


@pytest.fixture(scope="session")
async def engine():
    async for eng in create_test_engine():
        yield eng


@pytest.fixture(scope="session")
async def _setup_db(engine):
    await create_tables(engine)
    yield
    await drop_tables(engine)


@pytest.fixture
async def db_session(engine, _setup_db):
    """Per-test transactional session (rolled back after each test)."""
    async for session in create_test_session(engine):
        yield session


@pytest.fixture
async def file_app(db_session):
    """File service FastAPI app with test DB — no lifespan."""
    from app_factory import create_app
    from db.core.dependencies import get_db

    app = create_app(lifespan=None)
    app.dependency_overrides[get_db] = make_db_override(db_session)
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
async def client(file_app):
    """Async HTTP test client for file_service."""
    transport = ASGITransport(app=file_app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac


@pytest.fixture
def tmp_workspace(tmp_path):
    """Temporary workspace directory for file operations."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace
