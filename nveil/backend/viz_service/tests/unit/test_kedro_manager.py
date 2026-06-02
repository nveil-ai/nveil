# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for KedroVizManager — process lifecycle and notifications."""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from managers.kedro_manager import KedroVizManager


@pytest.fixture
def mgr():
    """KedroVizManager with mocked HTTP client."""
    client = AsyncMock()
    client.post = AsyncMock()
    return KedroVizManager(
        httpx_client=client,
        server_host="localhost",
        get_room_token=lambda: "tok_abc",
    )


def _mock_create_task():
    """Return a mock create_task that properly closes coroutines."""
    captured = {}

    def _create(coro):
        # Run the coroutine to completion in a new task
        # so it's not "unawaited", but capture the task for assertion
        task = asyncio.ensure_future(coro)
        captured["task"] = task
        return task

    return _create, captured


class TestStop:
    def test_stop_when_not_running(self, mgr):
        mgr.stop()
        assert mgr.kedro_viz_server is None
        assert mgr._kedro_viz_ready is False

    def test_stop_cancels_start_task(self, mgr):
        task = MagicMock()
        mgr._kedro_start_task = task
        mgr.stop()
        task.cancel.assert_called_once()
        assert mgr._kedro_start_task is None

    def test_stop_stops_server(self, mgr):
        server = MagicMock()
        mgr.kedro_viz_server = server
        mgr.stop()
        server.stop.assert_called_once()
        assert mgr.kedro_viz_server is None

    def test_stop_clears_state_port(self, mgr):
        state = MagicMock()
        server = MagicMock()
        mgr.kedro_viz_server = server
        mgr.stop(state)
        assert state.kedro_viz_port is None

    def test_stop_handles_server_stop_error(self, mgr):
        server = MagicMock()
        server.stop.side_effect = RuntimeError("boom")
        mgr.kedro_viz_server = server
        mgr.stop()  # should not raise
        assert mgr.kedro_viz_server is None

    def test_stop_resets_state_flags(self, mgr):
        mgr._kedro_viz_starting = True
        mgr._kedro_viz_ready = True
        mgr.stop()
        assert mgr._kedro_viz_starting is False
        assert mgr._kedro_viz_ready is False


class TestIsReady:
    def test_initially_not_ready(self, mgr):
        assert mgr.is_ready is False

    def test_ready_after_set(self, mgr):
        mgr._kedro_viz_ready = True
        assert mgr.is_ready is True


class TestNotifyReady:
    @pytest.mark.asyncio
    async def test_notify_sends_http_post(self, mgr):
        await mgr._notify_ready(4141)
        mgr.httpx_client.post.assert_awaited_once()
        call_args = mgr.httpx_client.post.call_args
        assert "kedro_viz_ready" in str(call_args)

    @pytest.mark.asyncio
    async def test_notify_catches_errors(self, mgr):
        mgr.httpx_client.post.side_effect = Exception("network error")
        await mgr._notify_ready(4141)  # should not raise


class TestRun:
    @pytest.mark.asyncio
    async def test_run_returns_early_when_no_pipeline_dir(self, mgr, tmp_path):
        """run() exits immediately if workspace/pipeline/ doesn't exist."""
        state = MagicMock()
        await mgr.run(tmp_path, state)
        assert mgr.kedro_viz_server is None
        assert mgr._kedro_viz_starting is False

    @pytest.mark.asyncio
    async def test_run_cancels_inflight_task(self, mgr, tmp_path):
        """run() cancels any in-flight startup task before proceeding."""
        (tmp_path / "pipeline").mkdir()

        # Use a real completed future so `await self._kedro_start_task` works
        inflight = asyncio.get_event_loop().create_future()
        inflight.set_result(None)
        mgr._kedro_start_task = inflight
        state = MagicMock()

        fake_server = MagicMock()
        fake_server.start.return_value = False
        with patch("choregraph.viz.KedroVizServer", return_value=fake_server):
            with patch("managers.kedro_manager.asynchronous") as mock_async:
                mock_async.create_task = MagicMock(side_effect=lambda c: c.close() or MagicMock())
                await mgr.run(tmp_path, state)

        # The old inflight task was consumed and cleared before the new cold start
        assert mgr._kedro_start_task is not inflight

    @pytest.mark.asyncio
    async def test_run_skips_if_already_starting(self, mgr, tmp_path):
        """run() skips cold start if _kedro_viz_starting is already True."""
        (tmp_path / "pipeline").mkdir()
        state = MagicMock()

        mgr._kedro_viz_starting = True  # simulate concurrent start

        with patch("choregraph.viz.KedroVizServer"):
            await mgr.run(tmp_path, state)

        # Should not have created a server
        assert mgr.kedro_viz_server is None

    @pytest.mark.asyncio
    async def test_run_cold_start_path(self, mgr, tmp_path):
        """run() enters cold start when no server is running."""
        (tmp_path / "pipeline").mkdir()
        state = MagicMock()

        fake_server = MagicMock()
        fake_server.start.return_value = True
        fake_server.wait_until_ready = AsyncMock(return_value=True)

        with patch("choregraph.viz.KedroVizServer", return_value=fake_server):
            with patch("managers.kedro_manager.asynchronous") as mock_async:
                # Capture and close the coroutine from create_task
                mock_async.create_task = MagicMock(side_effect=lambda c: c.close() or MagicMock())
                await mgr.run(tmp_path, state)

        assert mgr.kedro_viz_server is fake_server
        assert mgr._kedro_viz_starting is True

    @pytest.mark.asyncio
    async def test_run_hot_switch_path(self, mgr, tmp_path):
        """run() enters hot-switch when server is already running with a stable wrapper."""
        (tmp_path / "pipeline").mkdir()
        state = MagicMock()

        # Pre-set a running server with process + stable wrapper
        fake_server = MagicMock()
        fake_server.process = MagicMock()
        fake_server._stable_wrapper = MagicMock()
        mgr.kedro_viz_server = fake_server

        with patch("choregraph.viz.KedroVizServer"):
            with patch("managers.kedro_manager.asynchronous") as mock_async:
                mock_async.create_task = MagicMock(side_effect=lambda c: c.close() or MagicMock())
                await mgr.run(tmp_path, state)

        # Hot-switch resets ready state
        assert mgr._kedro_viz_ready is False
        assert state.kedro_viz_port is None
        # Server ref should still be the same (not replaced)
        assert mgr.kedro_viz_server is fake_server


class TestColdStart:
    @pytest.mark.asyncio
    async def test_cold_start_creates_server(self, mgr, tmp_path):
        """_cold_start creates a KedroVizServer and fires a startup task."""
        state = MagicMock()
        fake_server = MagicMock()

        with patch("choregraph.viz.KedroVizServer", return_value=fake_server):
            with patch("managers.kedro_manager.asynchronous") as mock_async:
                mock_async.create_task = MagicMock(side_effect=lambda c: c.close() or MagicMock())
                await mgr._cold_start(tmp_path / "pipeline", 4141, state)

        assert mgr.kedro_viz_server is fake_server
        assert mgr._kedro_start_task is not None

    @pytest.mark.asyncio
    async def test_cold_start_resets_flag_on_error(self, mgr, tmp_path):
        """If KedroVizServer() constructor raises, _kedro_viz_starting is reset."""
        state = MagicMock()
        mgr._kedro_viz_starting = True

        with patch("choregraph.viz.KedroVizServer", side_effect=RuntimeError("import error")):
            with pytest.raises(RuntimeError):
                await mgr._cold_start(tmp_path / "pipeline", 4141, state)

        assert mgr._kedro_viz_starting is False
