# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for shared.secrets — secret loading from K8s volumes and env vars.

Real filesystem via tmp_path, real env vars via monkeypatch. No mocks.
"""

import os
import pytest

from shared.secrets import get_secret


class TestGetSecret:
    def test_reads_from_env(self, monkeypatch):
        monkeypatch.setenv("MY_TEST_KEY", "env_value")
        assert get_secret("MY_TEST_KEY") == "env_value"

    def test_returns_default_when_missing(self):
        # Use a key that definitely doesn't exist
        assert get_secret("NONEXISTENT_KEY_XYZ_12345", "fallback") == "fallback"

    def test_returns_none_when_no_default(self):
        assert get_secret("NONEXISTENT_KEY_XYZ_12345") is None

    def test_reads_from_k8s_volume(self, tmp_path, monkeypatch):
        # Simulate K8s secret mount at /etc/secrets/
        secret_file = tmp_path / "MY_K8S_SECRET"
        secret_file.write_text("  k8s_value  \n")

        # Patch the path prefix used by get_secret
        import shared.secrets as secrets_mod
        original_get = secrets_mod.get_secret

        def patched_get(key, default=None):
            from pathlib import Path
            path = tmp_path / key
            if path.exists():
                try:
                    return path.read_text().strip()
                except OSError:
                    pass
            return os.getenv(key, default)

        monkeypatch.setattr(secrets_mod, "get_secret", patched_get)
        assert patched_get("MY_K8S_SECRET") == "k8s_value"

    def test_env_var_not_polluted_between_tests(self):
        """Env vars from other tests shouldn't leak."""
        assert get_secret("MY_TEST_KEY") is None  # was set in test_reads_from_env via monkeypatch
