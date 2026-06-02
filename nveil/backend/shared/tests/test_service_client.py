# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for shared.service_client — async HTTP client with retry and circuit breaker.

Uses respx to mock HTTP at the transport layer (no real network calls).
Real asyncio, real retry logic, real circuit breaker state.
"""

import asyncio
import time
import pytest
import httpx
import respx

from shared.service_client import ServiceClient, ServiceResponse, CircuitBreaker


# ---------------------------------------------------------------------------
# CircuitBreaker (pure state machine, no I/O)
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker(threshold=3)
        assert cb.is_open is False

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(threshold=2, recovery_seconds=60)
        cb.record_failure()
        assert cb.is_open is False
        cb.record_failure()
        assert cb.is_open is True

    def test_success_resets_count(self):
        cb = CircuitBreaker(threshold=2)
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        assert cb.is_open is False  # only 1 consecutive failure

    def test_recovers_after_timeout(self):
        cb = CircuitBreaker(threshold=1, recovery_seconds=0.0)
        cb.record_failure()
        assert cb.is_open is False  # recovery_seconds=0 → immediately allows probe


# ---------------------------------------------------------------------------
# ServiceClient
# ---------------------------------------------------------------------------


class TestServiceClientGet:
    @pytest.mark.asyncio
    async def test_success_200(self):
        client = ServiceClient(verify=False)
        with respx.mock:
            respx.get("https://svc/health").respond(200, json={"status": "ok"})
            resp = await client.get("https://svc/health")
        await client.close()

        assert resp.ok is True
        assert resp.status_code == 200
        assert resp.data == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_404_not_ok(self):
        client = ServiceClient(verify=False)
        with respx.mock:
            respx.get("https://svc/missing").respond(404, json={"error": "not found"})
            resp = await client.get("https://svc/missing")
        await client.close()

        assert resp.ok is False
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_text_response(self):
        client = ServiceClient(verify=False)
        with respx.mock:
            respx.get("https://svc/text").respond(200, text="plain text")
            resp = await client.get("https://svc/text")
        await client.close()

        assert resp.ok is True
        assert resp.data == "plain text"


class TestServiceClientPost:
    @pytest.mark.asyncio
    async def test_post_with_json(self):
        client = ServiceClient(verify=False)
        with respx.mock:
            route = respx.post("https://svc/action").respond(200, json={"done": True})
            resp = await client.post("https://svc/action", json={"key": "val"})
        await client.close()

        assert resp.ok is True
        assert resp.data == {"done": True}


class TestRetry:
    @pytest.mark.asyncio
    async def test_retries_on_500(self):
        client = ServiceClient(max_retries=2, backoff_base=0.01, verify=False)
        call_count = 0

        def side_effect(request):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return httpx.Response(500, json={"error": "internal"})
            return httpx.Response(200, json={"ok": True})

        with respx.mock:
            respx.post("https://svc/flaky").mock(side_effect=side_effect)
            resp = await client.post("https://svc/flaky")
        await client.close()

        assert resp.ok is True
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retries_on_connect_error(self):
        client = ServiceClient(max_retries=1, backoff_base=0.01, verify=False)
        call_count = 0

        def side_effect(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError("refused")
            return httpx.Response(200, json={"ok": True})

        with respx.mock:
            respx.get("https://svc/retry").mock(side_effect=side_effect)
            resp = await client.get("https://svc/retry")
        await client.close()

        assert resp.ok is True
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_exhausted_retries_returns_error(self):
        client = ServiceClient(max_retries=1, backoff_base=0.01, verify=False)
        with respx.mock:
            respx.get("https://svc/down").mock(side_effect=httpx.ConnectError("refused"))
            resp = await client.get("https://svc/down")
        await client.close()

        assert resp.ok is False
        assert resp.error_code == "SERVICE_UNAVAILABLE"


class TestCircuitBreakerIntegration:
    @pytest.mark.asyncio
    async def test_circuit_opens_after_failures(self):
        client = ServiceClient(
            max_retries=0, backoff_base=0.01, verify=False,
            circuit_threshold=2, circuit_recovery=60.0,
        )
        with respx.mock:
            respx.get("https://svc/fail").mock(side_effect=httpx.ConnectError("refused"))

            await client.get("https://svc/fail")
            await client.get("https://svc/fail")
            # Third call should be short-circuited
            resp = await client.get("https://svc/fail")
        await client.close()

        assert resp.ok is False
        assert resp.error_code == "CIRCUIT_OPEN"
