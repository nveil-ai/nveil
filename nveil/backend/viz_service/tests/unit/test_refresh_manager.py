# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for URLRefreshManager — interval scheduling, pause/resume, refresh."""

import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from managers.refresh_manager import URLRefreshManager


def _make_manager(**overrides):
    """Create a URLRefreshManager with safe defaults."""
    defaults = dict(
        get_mode=lambda: "chat",
        get_contexts=lambda: {},
        get_main_ctx=lambda: MagicMock(),
        build_viz_fn=lambda ctx, path: None,
        get_last_activity=lambda: datetime.now(),
        notify_host_fn=AsyncMock(),
    )
    defaults.update(overrides)
    return URLRefreshManager(**defaults)


def _mock_create_task():
    """Return a mock create_task that closes the coroutine to avoid warnings."""
    fake_task = MagicMock()

    def _create(coro):
        coro.close()  # prevent "coroutine was never awaited"
        return fake_task

    return _create, fake_task


class TestSetInterval:
    def test_set_interval_creates_task(self):
        mgr = _make_manager()
        create_fn, fake_task = _mock_create_task()
        with patch("managers.refresh_manager.asynchronous") as mock_async:
            mock_async.create_task = create_fn
            mgr.set_interval(30)
            assert mgr.interval == 30
            assert mgr._refresh_task is fake_task

    def test_set_interval_none_cancels(self):
        mgr = _make_manager()
        task = MagicMock()
        mgr._refresh_task = task
        mgr._refresh_interval = 30
        mgr.set_interval(None)
        task.cancel.assert_called_once()
        assert mgr._refresh_task is None
        assert mgr.interval is None

    def test_set_interval_zero_does_not_start(self):
        mgr = _make_manager()
        create_fn, _ = _mock_create_task()
        with patch("managers.refresh_manager.asynchronous") as mock_async:
            mock_async.create_task = create_fn
            mgr.set_interval(0)
            assert mgr._refresh_task is None

    def test_set_interval_replaces_existing_task(self):
        mgr = _make_manager()
        old_task = MagicMock()
        mgr._refresh_task = old_task
        create_fn, new_task = _mock_create_task()
        with patch("managers.refresh_manager.asynchronous") as mock_async:
            mock_async.create_task = create_fn
            mgr.set_interval(60)
            old_task.cancel.assert_called_once()
            assert mgr.interval == 60
            assert mgr._refresh_task is new_task


class TestPause:
    @pytest.mark.asyncio
    async def test_pause_cancels_task(self):
        mgr = _make_manager()
        task = AsyncMock()
        task.cancel = MagicMock()
        mgr._refresh_task = task
        mgr._refresh_interval = 15

        interval = await mgr.pause()
        assert interval == 15
        task.cancel.assert_called_once()
        assert mgr._refresh_task is None

    @pytest.mark.asyncio
    async def test_pause_noop_when_no_task(self):
        mgr = _make_manager()
        interval = await mgr.pause()
        assert interval is None


class TestResume:
    def test_resume_restarts_with_saved_interval(self):
        mgr = _make_manager()
        mgr._refresh_interval = 20
        create_fn, _ = _mock_create_task()
        with patch("managers.refresh_manager.asynchronous") as mock_async:
            mock_async.create_task = create_fn
            mgr.resume()
            assert mgr.interval == 20

    def test_resume_with_override_interval(self):
        mgr = _make_manager()
        mgr._refresh_interval = 10
        create_fn, _ = _mock_create_task()
        with patch("managers.refresh_manager.asynchronous") as mock_async:
            mock_async.create_task = create_fn
            mgr.resume(interval=45)
            assert mgr.interval == 45

    def test_resume_noop_when_no_interval(self):
        mgr = _make_manager()
        mgr._refresh_interval = None
        create_fn, _ = _mock_create_task()
        with patch("managers.refresh_manager.asynchronous") as mock_async:
            mock_async.create_task = create_fn
            mgr.resume()
            assert mgr._refresh_task is None


class TestRefreshContext:
    @pytest.mark.asyncio
    async def test_no_choregraph_returns_zero(self):
        mgr = _make_manager()
        ctx = MagicMock()
        ctx.choregraph = None
        result = await mgr.refresh_context(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_no_url_inputs_returns_zero(self):
        mgr = _make_manager()
        ctx = MagicMock()
        ctx.choregraph.spec.inputs = [MagicMock(url=None)]
        result = await mgr.refresh_context(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_no_workspace_returns_zero(self):
        mgr = _make_manager()
        ctx = MagicMock()
        ctx.choregraph.spec.inputs = [MagicMock(url="https://example.com")]
        ctx.workspace_path = None
        result = await mgr.refresh_context(ctx)
        assert result == 0


class TestIdleTimeout:
    @pytest.mark.asyncio
    async def test_idle_stops_loop(self):
        """Loop exits when idle timeout is exceeded."""
        old_time = datetime.now() - timedelta(seconds=300)
        mgr = _make_manager(get_last_activity=lambda: old_time)

        loop_task = asyncio.create_task(mgr._loop(interval=0))
        await asyncio.sleep(0.1)
        assert loop_task.done() or loop_task.cancelled()
