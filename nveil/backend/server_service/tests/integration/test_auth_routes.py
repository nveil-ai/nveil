# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Integration tests for auth routes — registration, login, CSRF."""

import pytest

from testing.factories import insert_user, DEFAULT_PASSWORD

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def mock_externals(monkeypatch, tmp_path):
    """Mock external services used by auth routes."""
    monkeypatch.setattr(
        "database.services.room_service._workspace_path",
        lambda o, r: tmp_path / str(o) / str(r),
    )


class TestCSRF:
    async def test_csrf_token_endpoint(self, client):
        resp = await client.get("/server/auth/csrf")
        assert resp.status_code == 200
        data = resp.json()
        assert "csrfToken" in data


class TestRegistration:
    async def test_register_success(self, client):
        resp = await client.post(
            "/server/auth/register",
            json={
                "name": "Test User",
                "email": "register@test.com",
                "password": "SecurePass123!",
                "accept_cgu": True,
                "accept_privacy": True,
            },
        )
        assert resp.status_code == 200

    async def test_register_duplicate_email(self, client, db_session):
        await insert_user(db_session, email="duplicate@test.com")
        resp = await client.post(
            "/server/auth/register",
            json={
                "name": "Second",
                "email": "duplicate@test.com",
                "password": "SecurePass123!",
                "accept_cgu": True,
                "accept_privacy": True,
            },
        )
        assert resp.status_code == 400


class TestLogin:
    async def test_wrong_password(self, client, db_session):
        await insert_user(db_session, email="login@test.com", email_verified=True)
        resp = await client.post(
            "/server/auth/login",
            data={"username": "login@test.com", "password": "WrongPass!"},
        )
        assert resp.status_code == 401


class TestCurrentUser:
    async def test_no_token_401(self, client):
        resp = await client.get("/server/auth/me")
        assert resp.status_code in (401, 403)


class TestHealthCheck:
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
