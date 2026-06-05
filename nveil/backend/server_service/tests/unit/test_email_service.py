# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for email service — OTP tracker."""

import time

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
