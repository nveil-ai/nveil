# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for ApiKeyService — key creation, validation, revocation."""

import pytest

from testing.factories import insert_user

pytestmark = pytest.mark.db


@pytest.fixture
def api_key_service(db_session):
    from database.services.api_key_service import ApiKeyService

    return ApiKeyService(db_session)


class TestCreateKey:
    async def test_returns_plaintext_and_model(self, api_key_service, db_session):
        user = await insert_user(db_session, email="apikey@test.com")
        plaintext, key_obj = await api_key_service.create_key(
            user_id=user.id, name="test-key", scopes=["read"]
        )
        assert isinstance(plaintext, str)
        assert key_obj is not None
        assert key_obj.name == "test-key"

    async def test_plaintext_starts_with_prefix(self, api_key_service, db_session):
        user = await insert_user(db_session, email="apikey2@test.com")
        plaintext, _ = await api_key_service.create_key(
            user_id=user.id, name="key2", scopes=["read"]
        )
        assert plaintext.startswith("nveil_")


class TestValidateKey:
    async def test_success(self, api_key_service, db_session):
        user = await insert_user(db_session, email="validate@test.com")
        plaintext, _ = await api_key_service.create_key(
            user_id=user.id, name="val-key", scopes=["read"]
        )
        result = await api_key_service.validate_key(plaintext)
        assert result is not None
        found_user, found_key = result
        assert str(found_user.id) == str(user.id)

    async def test_invalid_prefix(self, api_key_service):
        result = await api_key_service.validate_key("invalid_prefix_key")
        assert result is None

    async def test_nonexistent(self, api_key_service):
        result = await api_key_service.validate_key("nveil_nonexistent_key_value")
        assert result is None


class TestListKeys:
    async def test_returns_user_keys(self, api_key_service, db_session):
        user = await insert_user(db_session, email="list@test.com")
        await api_key_service.create_key(user_id=user.id, name="k1", scopes=["r"])
        await api_key_service.create_key(user_id=user.id, name="k2", scopes=["rw"])
        keys = await api_key_service.list_keys(user.id)
        assert len(keys) >= 2


class TestRevokeKey:
    async def test_success(self, api_key_service, db_session):
        user = await insert_user(db_session, email="revkey@test.com")
        _, key_obj = await api_key_service.create_key(
            user_id=user.id, name="to-revoke", scopes=["r"]
        )
        result = await api_key_service.revoke_key(key_obj.id, user.id)
        assert result is True

    async def test_wrong_owner(self, api_key_service, db_session):
        user1 = await insert_user(db_session, email="owner1@test.com")
        user2 = await insert_user(db_session, email="owner2@test.com")
        _, key_obj = await api_key_service.create_key(
            user_id=user1.id, name="owned", scopes=["r"]
        )
        with pytest.raises(Exception):
            await api_key_service.revoke_key(key_obj.id, user2.id)
