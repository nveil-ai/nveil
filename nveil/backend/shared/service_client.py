# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Shared async HTTP client with retry, circuit breaker, and structured response.

Usage (in any FastAPI service):

    from shared.service_client import ServiceClient, ServiceResponse

    client = ServiceClient()          # create once at startup
    resp = await client.post(url, json=payload, timeout=60.0)
    if resp.ok:
        data = resp.data
    else:
        log(resp.error)

    await client.close()              # call on shutdown
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx


@dataclass
class ServiceResponse:
    """Uniform response wrapper returned by ServiceClient."""

    ok: bool
    status_code: int = 0
    data: Any = None
    error: Optional[str] = None
    error_code: Optional[str] = None


class CircuitBreaker:
    """Simple circuit breaker: fast-fail after *threshold* consecutive failures."""

    def __init__(self, threshold: int = 3, recovery_seconds: float = 30.0):
        self._threshold = threshold
        self._recovery_seconds = recovery_seconds
        self._failures: int = 0
        self._opened_at: float = 0.0

    @property
    def is_open(self) -> bool:
        if self._failures < self._threshold:
            return False
        # Allow a probe after recovery window
        if time.monotonic() - self._opened_at >= self._recovery_seconds:
            return False
        return True

    def record_success(self):
        self._failures = 0

    def record_failure(self):
        self._failures += 1
        if self._failures >= self._threshold:
            self._opened_at = time.monotonic()


class ServiceClient:
    """Thin wrapper around ``httpx.AsyncClient`` with retry and circuit breaker.

    Parameters
    ----------
    max_retries : int
        Number of automatic retries on transient errors (connect / 5xx).
    backoff_base : float
        Base delay in seconds for exponential back-off between retries.
    circuit_threshold : int
        Consecutive failures before the circuit opens.
    circuit_recovery : float
        Seconds before the circuit allows a probe request.
    verify : bool
        TLS certificate verification (default True).
    """

    def __init__(
        self,
        *,
        max_retries: int = 1,
        backoff_base: float = 0.5,
        circuit_threshold: int = 3,
        circuit_recovery: float = 30.0,
        verify: bool = True,
    ):
        limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
        self._client = httpx.AsyncClient(limits=limits, verify=verify)
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        # Per-host circuit breakers
        self._breakers: dict[str, CircuitBreaker] = {}
        self._cb_threshold = circuit_threshold
        self._cb_recovery = circuit_recovery

    def _breaker_for(self, url: str) -> CircuitBreaker:
        host = httpx.URL(url).host or url
        if host not in self._breakers:
            self._breakers[host] = CircuitBreaker(
                threshold=self._cb_threshold,
                recovery_seconds=self._cb_recovery,
            )
        return self._breakers[host]

    async def request(
        self,
        method: str,
        url: str,
        *,
        timeout: float = 30.0,
        retries: int | None = None,
        **kwargs,
    ) -> ServiceResponse:
        cb = self._breaker_for(url)
        if cb.is_open:
            return ServiceResponse(
                ok=False,
                error="Circuit breaker open — service temporarily unavailable",
                error_code="CIRCUIT_OPEN",
            )

        max_attempts = (retries if retries is not None else self._max_retries) + 1
        last_error: str | None = None

        for attempt in range(max_attempts):
            try:
                resp = await self._client.request(
                    method, url, timeout=timeout, **kwargs
                )
                if resp.status_code >= 500 and attempt < max_attempts - 1:
                    last_error = f"HTTP {resp.status_code}"
                    await asyncio.sleep(self._backoff_base * (2**attempt))
                    continue

                cb.record_success()
                try:
                    data = resp.json()
                except Exception:
                    data = resp.text

                return ServiceResponse(
                    ok=200 <= resp.status_code < 400,
                    status_code=resp.status_code,
                    data=data,
                    error=None if resp.status_code < 400 else f"HTTP {resp.status_code}",
                )

            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                last_error = str(exc)
                cb.record_failure()
                if attempt < max_attempts - 1:
                    await asyncio.sleep(self._backoff_base * (2**attempt))
            except httpx.TimeoutException as exc:
                last_error = f"Timeout: {exc}"
                cb.record_failure()
                if attempt < max_attempts - 1:
                    await asyncio.sleep(self._backoff_base * (2**attempt))
            except Exception as exc:
                last_error = str(exc)
                cb.record_failure()
                break  # non-transient error, don't retry

        return ServiceResponse(
            ok=False,
            error=last_error or "Unknown error",
            error_code="SERVICE_UNAVAILABLE",
        )

    # Convenience methods
    async def get(self, url: str, **kwargs) -> ServiceResponse:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> ServiceResponse:
        return await self.request("POST", url, **kwargs)

    async def close(self):
        await self._client.aclose()
