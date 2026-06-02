# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for email service — OTP tracker (core) and ResendEmailProvider (plugin)."""

import time
from unittest.mock import AsyncMock, patch

import pytest

from database.services.email_service import OTPAttemptTracker


# ── OTPAttemptTracker (core) ─────────────────────────────────────────────


class TestOTPAttemptTracker:
    def test_first_attempt_allowed(self):
        tracker = OTPAttemptTracker()
        allowed, _, _ = tracker.check_and_record_attempt("user1")
        assert allowed is True

    def test_blocks_after_max_attempts(self, monkeypatch):
        tracker = OTPAttemptTracker(max_attempts=3, lockout_seconds=300)
        t = 1000.0
        for i in range(3):
            monkeypatch.setattr(time, "time", lambda _t=t + i * 10: _t)
            tracker.check_and_record_attempt("user1")
        monkeypatch.setattr(time, "time", lambda: t + 50)
        allowed, _, msg = tracker.check_and_record_attempt("user1")
        assert allowed is False
        assert "Maximum attempts" in msg

    def test_progressive_delay(self, monkeypatch):
        tracker = OTPAttemptTracker(max_attempts=10, lockout_seconds=300)
        t = 1000.0
        monkeypatch.setattr(time, "time", lambda: t)

        allowed, _, _ = tracker.check_and_record_attempt("user1")
        assert allowed is True

        allowed, wait, _ = tracker.check_and_record_attempt("user1")
        assert allowed is False
        assert wait > 0

    def test_clear_resets(self):
        tracker = OTPAttemptTracker(max_attempts=3, lockout_seconds=300)
        for _ in range(3):
            tracker.check_and_record_attempt("user1")
        tracker.clear_attempts("user1")
        allowed, _, _ = tracker.check_and_record_attempt("user1")
        assert allowed is True

    def test_is_locked(self, monkeypatch):
        tracker = OTPAttemptTracker(max_attempts=2, lockout_seconds=300)
        t = 1000.0
        monkeypatch.setattr(time, "time", lambda: t)
        tracker.check_and_record_attempt("user1")
        monkeypatch.setattr(time, "time", lambda: t + 100)
        tracker.check_and_record_attempt("user1")
        assert tracker.is_locked("user1") is True

    def test_not_locked_initially(self):
        tracker = OTPAttemptTracker()
        assert tracker.is_locked("user1") is False


# ── ResendEmailProvider (plugin — skipped if not installed) ──────────────


def _fake_get_secret(key, default=None):
    defaults = {"RESEND_API_KEY": "fake-key"}
    return defaults.get(key, default or "fake")


try:
    with patch("utils.get_secret", side_effect=_fake_get_secret):
        from nveilplugin.email import ResendEmailProvider
    _has_plugin = True
except ImportError:
    _has_plugin = False

needs_plugin = pytest.mark.skipif(not _has_plugin, reason="nveilplugin not installed")


@pytest.fixture
def email_svc(monkeypatch):
    monkeypatch.setattr("database.services.email_service.get_secret", lambda _: "fake-key")
    with patch("utils.get_secret", side_effect=_fake_get_secret):
        return ResendEmailProvider()


@needs_plugin
class TestGenerateCode:
    def test_returns_6_digit_string(self, email_svc):
        code = email_svc.generate_code("user-123")
        assert len(code) == 6
        assert code.isdigit()

    def test_same_window_same_code(self, email_svc):
        t = 1000.0
        c1 = email_svc.generate_code("user-123", timestamp=t)
        c2 = email_svc.generate_code("user-123", timestamp=t + 10)
        assert c1 == c2

    def test_different_window_different_code(self, email_svc):
        t = 1000.0
        c1 = email_svc.generate_code("user-123", timestamp=t)
        c2 = email_svc.generate_code("user-123", timestamp=t + 400)
        assert c1 != c2

    def test_different_users_different_code(self, email_svc):
        t = 1000.0
        c1 = email_svc.generate_code("user-a", timestamp=t)
        c2 = email_svc.generate_code("user-b", timestamp=t)
        assert c1 != c2

    def test_clears_attempts_on_generate(self, email_svc):
        email_svc.otp_tracker.check_and_record_attempt("user-123")
        email_svc.otp_tracker.check_and_record_attempt("user-123")
        email_svc.generate_code("user-123")
        assert not email_svc.otp_tracker.is_locked("user-123")


@needs_plugin
class TestVerifyCode:
    def test_valid_code_succeeds(self, email_svc, monkeypatch):
        t = 1000.0
        code = email_svc.generate_code("user-1", timestamp=t)
        monkeypatch.setattr(time, "time", lambda: t + 10)
        success, _ = email_svc.verify_code("user-1", code)
        assert success is True

    def test_invalid_code_fails(self, email_svc, monkeypatch):
        t = 1000.0
        email_svc.generate_code("user-1", timestamp=t)
        monkeypatch.setattr(time, "time", lambda: t + 10)
        success, msg = email_svc.verify_code("user-1", "000000")
        assert success is False
        assert "Invalid" in msg or "attempts" in msg

    def test_previous_window_accepted(self, email_svc, monkeypatch):
        t = 1000.0
        code = email_svc.generate_code("user-1", timestamp=t)
        next_window = ((int(t / 300) + 1) * 300) + 10
        monkeypatch.setattr(time, "time", lambda: next_window)
        success, _ = email_svc.verify_code("user-1", code)
        assert success is True

    def test_expired_window_rejected(self, email_svc, monkeypatch):
        t = 1000.0
        code = email_svc.generate_code("user-1", timestamp=t)
        far_future = t + 700
        monkeypatch.setattr(time, "time", lambda: far_future)
        success, _ = email_svc.verify_code("user-1", code)
        assert success is False


@needs_plugin
class TestSendEmails:
    async def test_send_verification_email(self, email_svc, monkeypatch):
        mock_send = AsyncMock(return_value={"id": "email-123"})
        monkeypatch.setattr(
            "database.services.email_service.resend.Emails.send_async",
            mock_send,
            raising=False,
        )
        result = await email_svc.send_verification_email("test@example.com", "123456", "Test User")
        assert result is not None
        mock_send.assert_awaited_once()
        params = mock_send.call_args[0][0]
        assert params["to"] == ["test@example.com"]
        assert "123456" in params["subject"]

    async def test_send_welcome_email(self, email_svc, monkeypatch):
        mock_send = AsyncMock(return_value={"id": "email-456"})
        monkeypatch.setattr(
            "database.services.email_service.resend.Emails.send_async",
            mock_send,
            raising=False,
        )
        result = await email_svc.send_welcome_email("test@example.com", "Test User")
        assert result is not None
        mock_send.assert_awaited_once()

    async def test_send_email_failure_returns_none(self, email_svc, monkeypatch):
        monkeypatch.setattr(
            "database.services.email_service.resend.Emails.send_async",
            AsyncMock(side_effect=Exception("API error")),
            raising=False,
        )
        result = await email_svc.send_verification_email("test@example.com", "123456", "Test User")
        assert result is None
