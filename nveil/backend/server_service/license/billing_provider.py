# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

from abc import ABC, abstractmethod
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.routing import APIRouter


class BillingProvider(ABC):
    """Interface for payment / checkout integration.

    Subclass this to integrate your own payment provider (Stripe, Paddle, etc.).
    See plugins/README.md for a full example.
    """

    @abstractmethod
    async def create_checkout_session(self, user, request: Request) -> dict: ...

    @abstractmethod
    async def handle_webhook(self, request: Request, signature: str) -> dict: ...

    @abstractmethod
    async def get_prices(self) -> list: ...

    @abstractmethod
    async def sync_license(self, user_id: str) -> Optional[dict]: ...

    @abstractmethod
    async def on_account_deleted(self, user_email: str) -> None: ...

    @abstractmethod
    def get_router(self) -> Optional[APIRouter]: ...


class NoOpBilling(BillingProvider):
    """Community default: billing is not available."""

    async def create_checkout_session(self, user, request: Request) -> dict:
        raise HTTPException(501, "Billing is not available in the community edition")

    async def handle_webhook(self, request: Request, signature: str) -> dict:
        return {"status": "ok"}

    async def get_prices(self) -> list:
        return []

    async def sync_license(self, user_id: str) -> Optional[dict]:
        return None

    async def on_account_deleted(self, user_email: str) -> None:
        pass

    def get_router(self) -> Optional[APIRouter]:
        return None


try:
    from nveilplugin.billing import StripeBillingProvider as _BillingImpl
except ImportError:
    _BillingImpl = NoOpBilling

billing_provider = _BillingImpl()
