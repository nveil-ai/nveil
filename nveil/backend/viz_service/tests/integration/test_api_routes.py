# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Integration tests for viz_service API routes (/viz/*)."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def _make_stub_app():
    """Create a minimal App stub for route testing."""
    app = MagicMock()
    app.room_id = "room_abc123"
    app.room_token = "tok_abc"
    app.owner_id = "owner_xyz"
    app.mode = "chat"
    app.pool_id = "pool_1"
    app.pod_ip = "127.0.0.1"
    app._last_activity = datetime.now()
    app.last_activity = datetime.now()
    app._kedro_viz_ready = False
    app.current_xml_path = "/workspace/specifications.xml"
    app.state = MagicMock()
    app.state.__getitem__ = MagicMock(return_value=None)
    app.state.__setitem__ = MagicMock()
    app.contexts = {"main": MagicMock()}
    app.update_activity = MagicMock()
    app._pause_refresh = AsyncMock(return_value=None)
    app._resume_refresh = MagicMock()
    app._assign_lock = __import__("asyncio").Lock()
    app._main_ctx = app.contexts["main"]
    app._main_ctx.state_proxy = MagicMock()
    app._main_ctx.vl.currentFrame = None
    return app


@pytest.fixture
async def client():
    """Async HTTP test client with a real FastAPI app and stubbed trame_app."""
    from api_routes import router

    fastapi_app = FastAPI()
    fastapi_app.include_router(router)
    fastapi_app.state.trame_app = _make_stub_app()

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac


@pytest.fixture
def trame_app(client):
    """Access the stub trame_app from the running FastAPI app."""
    # The client fixture creates the app — retrieve the stub
    return client._transport.app.state.trame_app


class TestHealth:
    async def test_health_returns_ok(self, client):
        resp = await client.get("/viz/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestStatus:
    async def test_status_returns_room_info(self, client, trame_app):
        resp = await client.get("/viz/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["room_id"] == "room_abc123"
        assert data["owner_id"] == "owner_xyz"
        assert data["mode"] == "chat"
        assert "idle_seconds" in data


class TestCurrentSpec:
    async def test_returns_filename(self, client):
        resp = await client.get("/viz/current-spec")
        assert resp.status_code == 200
        assert resp.json()["current_xml_filename"] == "specifications.xml"

    async def test_returns_none_when_no_spec(self, client, trame_app):
        trame_app.current_xml_path = None
        resp = await client.get("/viz/current-spec")
        assert resp.json()["current_xml_filename"] is None


class TestExportSpec:
    async def test_returns_400_when_no_active_spec(self, client, trame_app):
        # Without a parsed VisuSpec the endpoint must reject — nothing to bake.
        trame_app.contexts["main"].vl = None
        resp = await client.post("/viz/export-spec")
        assert resp.status_code == 400


class TestSetPlotTheme:
    async def test_valid_theme(self, client, trame_app):
        trame_app.contexts["main"].state_key = lambda k: f"main_{k}"
        trame_app.contexts["main"].vl.currentFrame = None

        resp = await client.post("/viz/set_plot_theme", json={"theme": "white"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["theme"] == "white"

    async def test_invalid_theme(self, client):
        resp = await client.post("/viz/set_plot_theme", json={"theme": "neon"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"


class TestHandleCommand:
    async def test_build_viz_command(self, client, trame_app):
        trame_app.build_viz_from_ui = MagicMock(return_value="/gen.xml")
        trame_app.state.__getitem__ = lambda self_mock, key: None  # viz_error = None

        with patch("api_routes.helper.notify_host", new_callable=AsyncMock):
            resp = await client.post("/viz/handle_command", json={
                "room_token": "tok_abc",
                "command": "build_viz",
                "xml_path": "/workspace/spec.xml",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["viz_file"] == "/gen.xml"
        trame_app.build_viz_from_ui.assert_called_once_with("/workspace/spec.xml")

    async def test_stale_room_rejected(self, client, trame_app):
        resp = await client.post("/viz/handle_command", json={
            "room_token": "tok_OLD",
            "command": "build_viz",
            "xml_path": "/spec.xml",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "stale_room"


class TestReleaseRoom:
    async def test_release_when_assigned(self, client, trame_app):
        trame_app.release_room = MagicMock()
        resp = await client.post("/viz/release_room")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "released"
        assert data["old_room_id"] == "room_abc123"
        trame_app.release_room.assert_called_once()

    async def test_release_when_idle(self, client, trame_app):
        trame_app.room_id = None
        resp = await client.post("/viz/release_room")
        assert resp.status_code == 200
        assert resp.json()["status"] == "already_idle"


class TestSetRefreshInterval:
    async def test_set_valid_interval(self, client, trame_app):
        trame_app.set_refresh_interval = MagicMock()
        resp = await client.post("/viz/set_refresh_interval", json={"interval": 30})
        assert resp.status_code == 200
        assert resp.json()["interval"] == 30
        trame_app.set_refresh_interval.assert_called_once_with(30)

    async def test_set_disable(self, client, trame_app):
        trame_app.set_refresh_interval = MagicMock()
        resp = await client.post("/viz/set_refresh_interval", json={"interval": 0})
        assert resp.status_code == 200
        assert resp.json()["interval"] is None

    async def test_minimum_5_seconds(self, client, trame_app):
        trame_app.set_refresh_interval = MagicMock()
        resp = await client.post("/viz/set_refresh_interval", json={"interval": 2})
        assert resp.status_code == 200
        assert resp.json()["interval"] == 5
