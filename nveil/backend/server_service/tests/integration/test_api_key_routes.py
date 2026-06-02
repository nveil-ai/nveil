# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Integration tests for API key routes — create, list, revoke."""

import pytest

from testing.factories import insert_user

pytestmark = pytest.mark.integration


class TestCreateApiKey:
    async def test_success(self, client, override_auth, db_session):
        user = await insert_user(db_session, email="apikey_route@test.com")
        override_auth(user)
        resp = await client.post(
            "/api/v1/keys",
            json={"name": "test-key", "scopes": ["visualization:generate"]},
        )
        assert resp.status_code in (200, 201)

    async def test_unauthenticated_401(self, client):
        resp = await client.post(
            "/api/v1/keys", json={"name": "fail", "scopes": ["visualization:generate"]}
        )
        assert resp.status_code in (401, 403)


class TestListApiKeys:
    async def test_empty_list(self, client, override_auth, db_session):
        user = await insert_user(db_session, email="list_route@test.com")
        override_auth(user)
        resp = await client.get("/api/v1/keys")
        assert resp.status_code == 200
