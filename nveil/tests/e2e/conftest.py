# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Fixtures for end-to-end tests.

E2E tests require running services (server, ai, file).
Start them via `make up` or `docker compose up` before running these tests.
"""

import os

import pytest
import httpx


BASE_URL = os.environ.get("E2E_BASE_URL", "https://localhost:8000")


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def e2e_client(base_url):
    """HTTP client for e2e tests against running services."""
    with httpx.Client(base_url=base_url, verify=False, timeout=30) as client:
        yield client
