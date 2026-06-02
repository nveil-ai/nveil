# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""URL auto-refresh scheduler — periodically re-fetch URL sources and rebuild."""

import asyncio
from datetime import datetime
from typing import Optional, Callable

from logger import INFO, WARNING, logger
from trame.app import asynchronous


class URLRefreshManager:
    """Manages periodic re-fetching of URL-based data sources.

    Args:
        get_mode: Callable returning current mode ("chat" or "dashboard").
        get_contexts: Callable returning the contexts dict.
        get_main_ctx: Callable returning the main VizContext.
        build_viz_fn: Callback to rebuild viz: (ctx, xml_path) -> None.
        get_last_activity: Callable returning datetime of last user activity.
        notify_host_fn: Async callback for server notifications.
    """

    IDLE_TIMEOUT = 120  # seconds

    def __init__(
        self,
        get_mode: Callable,
        get_contexts: Callable,
        get_main_ctx: Callable,
        build_viz_fn: Callable,
        get_last_activity: Callable,
        notify_host_fn: Callable,
    ):
        self._get_mode = get_mode
        self._get_contexts = get_contexts
        self._get_main_ctx = get_main_ctx
        self._build_viz = build_viz_fn
        self._get_last_activity = get_last_activity
        self._notify_host = notify_host_fn

        self._refresh_task: Optional[asyncio.Task] = None
        self._refresh_interval: Optional[int] = None

    @property
    def interval(self) -> Optional[int]:
        return self._refresh_interval

    def set_interval(self, interval_seconds: Optional[int]):
        """Set or cancel the URL auto-refresh interval."""
        if self._refresh_task is not None:
            self._refresh_task.cancel()
            self._refresh_task = None
            logger().logp(INFO, "URL refresh scheduler cancelled")

        self._refresh_interval = interval_seconds

        if interval_seconds and interval_seconds > 0:
            self._refresh_task = asynchronous.create_task(
                self._loop(interval_seconds)
            )
            logger().logp(INFO, f"URL refresh scheduler started: every {interval_seconds}s")

    async def pause(self) -> Optional[int]:
        """Cancel the refresh loop. Returns the saved interval for resume."""
        interval = self._refresh_interval
        if self._refresh_task is not None:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except (asyncio.CancelledError, Exception):
                pass
            self._refresh_task = None
            logger().logp(INFO, "Refresh paused")
        return interval

    def resume(self, interval: Optional[int] = None):
        """Restart the refresh loop."""
        iv = interval if interval is not None else self._refresh_interval
        if iv and iv > 0:
            self.set_interval(iv)

    async def refresh_context(self, ctx) -> int:
        """Re-fetch URL sources and rebuild visualization for a single context.

        Returns the number of fetched URL inputs, or 0 if nothing changed.
        """
        if not ctx.choregraph:
            return 0

        url_inputs = [inp for inp in ctx.choregraph.spec.inputs if inp.url]
        if not url_inputs:
            return 0

        from choregraph.fetcher import fetch_inputs
        from choregraph.connectors import DiveConnector

        ws = ctx.workspace_path
        if not ws:
            return 0

        fetched = fetch_inputs(ctx.choregraph.spec.inputs, ws)
        if fetched == 0:
            return 0

        cg_xml_path = ws / "choregraph.xml"
        ctx.choregraph.export_to_xml(cg_xml_path)
        ctx.choregraph._ensure_wrapper()

        run_success, run_error = ctx.choregraph.run(lazy=True)
        if not run_success:
            logger().logp(WARNING, f"Refresh pipeline failed: {run_error}")
            return 0

        spec_xml_path = ws / "specifications.xml"
        DiveConnector.from_choregraph(ctx.choregraph).update_visuspec_xml(
            save_to_path=str(spec_xml_path)
        )

        if ctx.current_xml_path:
            self._build_viz(ctx, ctx.current_xml_path)

        return fetched

    async def _loop(self, interval: int):
        """Periodically re-fetch URL sources and rebuild visualization."""
        try:
            while True:
                await asyncio.sleep(interval)

                idle_seconds = (datetime.now() - self._get_last_activity()).total_seconds()
                if idle_seconds > self.IDLE_TIMEOUT:
                    logger().logp(INFO, f"Auto-refresh paused: no activity for {idle_seconds:.0f}s")
                    self._refresh_task = None
                    return

                total_fetched = 0
                try:
                    if self._get_mode() == "dashboard":
                        for panel_id, ctx in self._get_contexts().items():
                            if panel_id == "main":
                                continue
                            total_fetched += await self.refresh_context(ctx)
                    else:
                        total_fetched = await self.refresh_context(self._get_main_ctx())

                    if total_fetched > 0:
                        await self._notify_host(total_fetched)
                        logger().logp(INFO, f"Auto-refresh: {total_fetched} URL sources updated")
                except Exception as e:
                    logger().logp(WARNING, f"Auto-refresh error: {e}")

        except asyncio.CancelledError:
            logger().logp(INFO, "URL refresh loop cancelled")
