# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for community-mode provider defaults.

Verifies that LogOnlyEmail, CommunityLicense, and NoOpBilling
implement their ABCs correctly and behave as expected when
the nveilplugin package is not installed.
"""

import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock

from database.services.email_service import LogOnlyEmail, EmailProvider
from database.services.license_provider import CommunityLicense, LicenseProvider
from license.billing_provider import NoOpBilling, BillingProvider


# ── LogOnlyEmail ─────────────────────────────────────────────────

class TestLogOnlyEmail:
    def setup_method(self):
        self.email = LogOnlyEmail()

    def test_is_email_provider(self):
        assert isinstance(self.email, EmailProvider)

    def test_generate_code_returns_zeros(self):
        assert self.email.generate_code("user-1") == "000000"

    def test_verify_code_accepts_zeros(self):
        ok, err = self.email.verify_code("user-1", "000000")
        assert ok is True
        assert err is None

    def test_verify_code_rejects_wrong(self):
        ok, _ = self.email.verify_code("user-1", "999999")
        assert ok is False

    def test_can_regenerate_always_true(self):
        allowed, wait = self.email.can_regenerate_code("user-1")
        assert allowed is True
        assert wait == 0

    @pytest.mark.asyncio
    async def test_send_verification_email(self):
        result = await self.email.send_verification_email("a@b.com", "000000", "User")
        assert result is None

    @pytest.mark.asyncio
    async def test_send_password_reset_email(self):
        result = await self.email.send_password_reset_email("a@b.com", "000000", "User")
        assert result is None

    @pytest.mark.asyncio
    async def test_send_welcome_email(self):
        result = await self.email.send_welcome_email("a@b.com", "User")
        assert result is None

    @pytest.mark.asyncio
    async def test_send_license_subscription_email(self):
        result = await self.email.send_license_subscription_email("a@b.com", "User", "Pro", "monthly")
        assert result is None

    @pytest.mark.asyncio
    async def test_send_account_deleted_email(self):
        result = await self.email.send_account_deleted_email("a@b.com", "User")
        assert result is None


# ── CommunityLicense ─────────────────────────────────────────────

class TestCommunityLicense:
    def setup_method(self):
        self.license = CommunityLicense()

    def test_is_license_provider(self):
        assert isinstance(self.license, LicenseProvider)

    @pytest.mark.asyncio
    async def test_license_info_structure(self):
        info = await self.license.get_license_info("user-1")
        assert info["license_name"] == "Community"
        assert info["is_active"] is True
        assert info["max_seats"] == 999
        assert info["is_trial"] is False
        assert isinstance(info["features"], dict)

    @pytest.mark.asyncio
    async def test_check_feature_always_true(self):
        assert await self.license.check_feature("user-1", "csv") is True
        assert await self.license.check_feature("user-1", "nonexistent") is True

    @pytest.mark.asyncio
    async def test_get_feature_value_returns_none(self):
        assert await self.license.get_feature_value("user-1", "upload") is None

    @pytest.mark.asyncio
    async def test_on_user_created_noop(self):
        await self.license.on_user_created("user-1")


# ── NoOpBilling ──────────────────────────────────────────────────

class TestNoOpBilling:
    def setup_method(self):
        self.billing = NoOpBilling()

    def test_is_billing_provider(self):
        assert isinstance(self.billing, BillingProvider)

    @pytest.mark.asyncio
    async def test_create_checkout_raises_501(self):
        with pytest.raises(HTTPException) as exc_info:
            await self.billing.create_checkout_session(MagicMock(), MagicMock())
        assert exc_info.value.status_code == 501

    @pytest.mark.asyncio
    async def test_handle_webhook_returns_ok(self):
        result = await self.billing.handle_webhook(MagicMock(), "sig")
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_get_prices_empty(self):
        assert await self.billing.get_prices() == []

    @pytest.mark.asyncio
    async def test_sync_license_returns_none(self):
        assert await self.billing.sync_license("user-1") is None

    @pytest.mark.asyncio
    async def test_on_account_deleted_noop(self):
        await self.billing.on_account_deleted("a@b.com")

    def test_get_router_returns_none(self):
        assert self.billing.get_router() is None
