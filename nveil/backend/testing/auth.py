# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Shared authentication helpers for backend service tests.

Usage in a service conftest.py:

    import pytest
    from testing.auth import make_auth_headers, make_room_token_cookie

    @pytest.fixture
    def auth_headers():
        return make_auth_headers(user_id="test-user-id")
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

import jwt


# Test-only secret — matches the SECRET_KEY used in test environment.
# Override via TEST_SECRET_KEY env var if your test .env differs.
TEST_SECRET_KEY = "test-secret-key-for-testing-only-32B!"  # 36 bytes — avoids PyJWT InsecureKeyLengthWarning
TEST_ALGORITHM = "HS256"


def make_auth_headers(
    user_id: str = "test-user-id",
    expires_delta: Optional[timedelta] = None,
    secret_key: str = TEST_SECRET_KEY,
) -> dict[str, str]:
    """Generate Authorization headers with a valid JWT Bearer token."""
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=1))
    payload = {"sub": user_id, "exp": expire}
    token = jwt.encode(payload, secret_key, algorithm=TEST_ALGORITHM)
    return {"Authorization": f"Bearer {token}"}


def make_room_token() -> str:
    """Generate a random room token UUID string."""
    return str(uuid4())


def make_room_token_cookie(token: Optional[str] = None) -> dict[str, str]:
    """Generate a room_token cookie dict for httpx client."""
    token = token or make_room_token()
    return {"room_token": token}
