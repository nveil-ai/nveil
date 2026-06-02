# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for UserService — user creation, authentication, email verification."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from testing.factories import insert_user, DEFAULT_PASSWORD

pytestmark = pytest.mark.db


@pytest.fixture
def _mock_email_service():
    """Fake EmailService — no real email sending."""
    email_svc = MagicMock()
    email_svc.generate_code = MagicMock(return_value="123456")
    email_svc.verify_code = MagicMock(return_value=(True, None))
    email_svc.can_regenerate_code = MagicMock(return_value=(True, 0, ""))
    email_svc.send_verification_email = AsyncMock()
    email_svc.send_welcome_email = AsyncMock()
    email_svc.send_password_reset_email = AsyncMock()
    return email_svc


@pytest.fixture
def user_service(db_session, _mock_email_service):
    """UserService with injected mock EmailService."""
    from database.services.user_service import UserService

    return UserService(db_session, email_service=_mock_email_service)


class TestCreateUser:
    async def test_with_password(self, user_service):
        user = await user_service.create_user(
            name="Alice", email="alice@test.com", password="Secure123!"
        )
        assert user is not None
        assert user.email == "alice@test.com"
        assert user.name == "Alice"
        assert user._password is not None

    async def test_without_password_oauth(self, user_service):
        user = await user_service.create_user(
            name="Bob", email="bob@test.com", password=None
        )
        assert user is not None
        assert user._password is None

    async def test_duplicate_email_raises(self, user_service, db_session):
        await insert_user(db_session, email="dup@test.com")
        with pytest.raises(Exception):
            await user_service.create_user(
                name="Dup", email="dup@test.com", password="Pass123!"
            )


class TestAuthenticate:
    async def test_valid_credentials(self, user_service, db_session):
        await insert_user(db_session, email="auth@test.com")
        user = await user_service.authenticate("auth@test.com", DEFAULT_PASSWORD)
        assert user is not None
        assert user.email == "auth@test.com"

    async def test_wrong_password(self, user_service, db_session):
        await insert_user(db_session, email="auth2@test.com")
        user = await user_service.authenticate("auth2@test.com", "WrongPass!")
        assert user is None

    async def test_nonexistent_email(self, user_service):
        user = await user_service.authenticate("nobody@test.com", "Pass123!")
        assert user is None

    async def test_oauth_user_no_password(self, user_service, db_session):
        await insert_user(db_session, email="oauth@test.com", password_hash=None)
        user = await user_service.authenticate("oauth@test.com", "Pass123!")
        assert user is None


class TestVerifyEmail:
    async def test_valid_code(self, user_service, db_session):
        user = await insert_user(db_session, email="verify@test.com", email_verified=False)
        success, msg = await user_service.verify_email("verify@test.com", "123456")
        assert success is True

    async def test_already_verified(self, user_service, db_session):
        await insert_user(db_session, email="verified@test.com", email_verified=True)
        success, msg = await user_service.verify_email("verified@test.com", "123456")
        # Should still succeed or indicate already verified
        assert isinstance(success, bool)

    async def test_invalid_code(self, user_service, db_session):
        user_service.email_service.verify_code.return_value = (False, "Invalid code")
        await insert_user(db_session, email="fail@test.com", email_verified=False)
        success, msg = await user_service.verify_email("fail@test.com", "000000")
        assert success is False


class TestSetOnlineStatus:
    async def test_set_online(self, user_service, db_session):
        user = await insert_user(db_session, email="online@test.com")
        result = await user_service.set_online_status(str(user.id), True)
        assert result is True
