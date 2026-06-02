# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for TokenService — JWT creation, refresh token rotation, revocation."""

import pytest
from unittest.mock import MagicMock

from testing.factories import insert_user

pytestmark = pytest.mark.db


@pytest.fixture
def token_service(db_session, monkeypatch):
    """TokenService with test secrets."""
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-testing-only")
    monkeypatch.setenv("ALGORITHM", "HS256")
    from database.services.token_service import TokenService, JWTService

    # Ensure JWTService uses test values
    monkeypatch.setattr(JWTService, "SECRET_KEY", "test-secret-key-for-testing-only")
    monkeypatch.setattr(JWTService, "ALGORITHM", "HS256")
    return TokenService(db_session)


@pytest.fixture
def jwt_service(monkeypatch):
    from database.services.token_service import JWTService

    monkeypatch.setattr(JWTService, "SECRET_KEY", "test-secret-key-for-testing-only")
    monkeypatch.setattr(JWTService, "ALGORITHM", "HS256")
    return JWTService


class TestJWT:
    def test_create_and_decode_roundtrip(self, jwt_service):
        payload = {"sub": "user-123", "email": "test@test.com", "type": "access"}
        token = jwt_service.create_access_token(payload)
        assert isinstance(token, str)
        decoded = jwt_service.decode_access_token(token)
        assert decoded is not None
        assert decoded["sub"] == "user-123"

    def test_decode_invalid_token(self, jwt_service):
        result = jwt_service.decode_access_token("not.a.valid.token")
        assert result is None

    def test_decode_wrong_secret(self, jwt_service, monkeypatch):
        payload = {"sub": "user-123", "type": "access"}
        token = jwt_service.create_access_token(payload)
        monkeypatch.setattr(jwt_service, "SECRET_KEY", "different-secret-key-that-is-long-enough!")
        result = jwt_service.decode_access_token(token)
        assert result is None


class TestIssueTokenPair:
    async def test_returns_strings(self, token_service, db_session):
        user = await insert_user(db_session, email="token@test.com")
        refresh, access = await token_service.issue_token_pair(user)
        assert isinstance(refresh, str)
        assert isinstance(access, str)
        assert len(refresh) > 10
        assert len(access) > 10


class TestRotateToken:
    async def test_success(self, token_service, db_session):
        user = await insert_user(db_session, email="rotate@test.com")
        refresh, _ = await token_service.issue_token_pair(user)
        new_refresh, new_access = await token_service.rotate_token(refresh)
        assert isinstance(new_refresh, str)
        assert new_refresh != refresh  # new token issued

    async def test_reuse_detection(self, token_service, db_session):
        user = await insert_user(db_session, email="reuse@test.com")
        refresh, _ = await token_service.issue_token_pair(user)
        # First rotation — OK
        await token_service.rotate_token(refresh)
        # Second rotation with same token — should fail (reuse detection)
        with pytest.raises(Exception):
            await token_service.rotate_token(refresh)


class TestRevokeToken:
    async def test_revoke_success(self, token_service, db_session):
        user = await insert_user(db_session, email="revoke@test.com")
        refresh, _ = await token_service.issue_token_pair(user)
        result = await token_service.revoke_token(refresh)
        assert result is True

    async def test_revoke_nonexistent(self, token_service):
        result = await token_service.revoke_token("nonexistent-token")
        assert result is False

    async def test_revoke_all_user_tokens(self, token_service, db_session):
        user = await insert_user(db_session, email="revokeall@test.com")
        await token_service.issue_token_pair(user)
        await token_service.issue_token_pair(user)
        count = await token_service.revoke_all_user_tokens(str(user.id))
        assert count >= 2
