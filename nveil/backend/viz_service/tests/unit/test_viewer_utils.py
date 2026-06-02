# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for viewer_utils — file checks, port finding, host notification."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from helpers.viewer_utils import file_exists, find_available_port, notify_host


class TestFileExists:
    def test_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert file_exists(str(f)) is True

    def test_nonexistent_file(self, tmp_path):
        assert file_exists(str(tmp_path / "nope.txt")) is False

    def test_directory_returns_false(self, tmp_path):
        assert file_exists(str(tmp_path)) is False


class TestFindAvailablePort:
    def test_finds_free_port(self):
        # Port 59999 is very unlikely to be in use
        port = find_available_port(59999)
        assert isinstance(port, int)
        assert port >= 59999


class TestNotifyHost:
    @pytest.mark.asyncio
    async def test_success(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=MagicMock(ok=True))
        await notify_host(
            "localhost", "room-token-123", "test_message",
            client=mock_client,
        )
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_failure_no_raise(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
        # Should not raise — notify_host catches exceptions
        await notify_host(
            "localhost", "room-token-123", "test_message",
            client=mock_client,
        )
