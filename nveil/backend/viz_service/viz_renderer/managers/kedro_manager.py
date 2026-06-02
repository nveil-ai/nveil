# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Kedro Viz process lifecycle — cold start, hot-switch, stop, notifications."""

import asyncio
from logging import ERROR, WARNING
from pathlib import Path
from threading import Lock
from typing import Optional

from logger import INFO, logger
from trame.app import asynchronous


class KedroVizManager:
    """Manages the Kedro Viz subprocess lifecycle.

    Handles cold starts, hot-switches (config swap + autoreload), stopping,
    and server-ready notifications.

    Args:
        httpx_client: Async HTTP client for notifications.
        server_host: Hostname of the server service (for notifications).
        get_room_token: Callable returning the current room token.
    """

    def __init__(self, httpx_client, server_host: str, get_room_token):
        self.httpx_client = httpx_client
        self.server_host = server_host
        self._get_room_token = get_room_token

        self.kedro_viz_server = None
        self._kedro_start_task: Optional[asyncio.Task] = None
        self._kedro_viz_starting = False
        self._kedro_viz_ready = False
        self._kedro_viz_lock = Lock()

    @property
    def is_ready(self) -> bool:
        return self._kedro_viz_ready

    def stop(self, state=None):
        """Stop the Kedro Viz server if running.

        Args:
            state: Optional trame state to clear kedro_viz_port.
        """
        if self._kedro_start_task is not None:
            self._kedro_start_task.cancel()
            self._kedro_start_task = None
        if self.kedro_viz_server is not None:
            try:
                self.kedro_viz_server.stop()
                logger().logp(INFO, "Kedro Viz server stopped")
            except Exception as e:
                logger().logp(WARNING, f"Failed to stop Kedro Viz: {e}")
            self.kedro_viz_server = None
        with self._kedro_viz_lock:
            self._kedro_viz_starting = False
            self._kedro_viz_ready = False
        if state is not None:
            state.kedro_viz_port = None

    async def run(self, workspace_path, state, choregraph_xml_path=None):
        """Start or hot-switch Kedro Viz server.

        Uses fixed port 4141. Hot-switches reuse the running process by
        swapping config files and letting autoreload restart the child.

        Args:
            workspace_path: Path to workspace containing pipeline/.
            state: Trame state (to set kedro_viz_port).
            choregraph_xml_path: Optional path for label mapping.
        """
        from choregraph.viz import KedroVizServer

        viz_wrapper_path = Path(workspace_path) / "pipeline"
        if not viz_wrapper_path.exists():
            logger().logp(WARNING, f"choregraph.viz: pipeline not found at {viz_wrapper_path}")
            return

        kedro_port = 4141

        # Cancel any in-flight startup / switch task
        if self._kedro_start_task is not None:
            self._kedro_start_task.cancel()
            try:
                await self._kedro_start_task
            except (asyncio.CancelledError, Exception):
                pass
            self._kedro_start_task = None

        # HOT-SWITCH: server already running
        if (
            self.kedro_viz_server is not None
            and self.kedro_viz_server.process is not None
            and self.kedro_viz_server._stable_wrapper is not None
        ):
            server_ref = self.kedro_viz_server
            self._kedro_viz_ready = False
            state.kedro_viz_port = None

            async def do_switch():
                try:
                    server_ref.switch_project(viz_wrapper_path)
                    logger().logp(INFO, "Kedro Viz hot-switch: files synced, waiting for autoreload…")
                    if self.kedro_viz_server is not server_ref:
                        return
                    ok = await server_ref.wait_for_switch(timeout=20.0)
                    if self.kedro_viz_server is not server_ref:
                        return
                    if ok:
                        state.kedro_viz_port = kedro_port
                        self._kedro_viz_ready = True
                        logger().logp(INFO, f"Kedro Viz hot-switched on port {kedro_port}")
                        await self._notify_ready(kedro_port)
                        return
                    logger().logp(WARNING, "Hot-switch timed out, falling back to cold restart")
                    self.stop(state)
                    await self._cold_start(viz_wrapper_path, kedro_port, state)
                except asyncio.CancelledError:
                    logger().logp(INFO, "Kedro Viz switch task cancelled")
                except Exception as e:
                    logger().logp(ERROR, f"Kedro Viz switch error: {e}")

            self._kedro_start_task = asynchronous.create_task(do_switch())
            return

        # COLD START
        with self._kedro_viz_lock:
            if self._kedro_viz_starting:
                logger().logp(WARNING, "Kedro Viz start already in progress, skipping")
                return
            self._kedro_viz_starting = True

        await self._cold_start(viz_wrapper_path, kedro_port, state)

    async def _cold_start(self, viz_wrapper_path: Path, kedro_port: int, state):
        """Spawn a new Kedro Viz process."""
        from choregraph.viz import KedroVizServer

        try:
            self.kedro_viz_server = KedroVizServer(port=kedro_port)
            server_ref = self.kedro_viz_server

            async def start_server():
                try:
                    started = server_ref.start(viz_wrapper_path)
                    if started:
                        logger().logp(INFO, f"Kedro Viz server starting on port {kedro_port}...")
                        if await server_ref.wait_until_ready(timeout=30.0, poll_interval=0.5):
                            if self.kedro_viz_server is not server_ref:
                                return
                            state.kedro_viz_port = kedro_port
                            self._kedro_viz_ready = True
                            logger().logp(INFO, f"Kedro Viz server ready on port {kedro_port}")
                            await self._notify_ready(kedro_port)
                        else:
                            logger().logp(WARNING, "Kedro Viz slow to start, extended polling...")
                            if await server_ref.wait_until_ready(timeout=60.0, poll_interval=2.0):
                                if self.kedro_viz_server is not server_ref:
                                    return
                                state.kedro_viz_port = kedro_port
                                self._kedro_viz_ready = True
                                logger().logp(INFO, f"Kedro Viz server ready (late) on port {kedro_port}")
                                await self._notify_ready(kedro_port)
                            else:
                                logger().logp(WARNING, "Kedro Viz server failed to start within 90s")
                except asyncio.CancelledError:
                    logger().logp(INFO, "Kedro Viz start_server task cancelled")
                except Exception as e:
                    logger().logp(ERROR, f"Error starting Kedro Viz: {e}")

            self._kedro_start_task = asynchronous.create_task(start_server())
        except Exception as e:
            with self._kedro_viz_lock:
                self._kedro_viz_starting = False
            raise

    async def _notify_ready(self, port: int):
        """Notify the server that Kedro Viz is ready."""
        try:
            await self.httpx_client.post(
                f"https://{self.server_host}:8000/viz/notify",
                json={
                    "room_token": self._get_room_token(),
                    "event": "kedro_viz_ready",
                    "port": port,
                },
                timeout=5,
            )
        except Exception as e:
            logger().logp(WARNING, f"Failed to notify Kedro Viz ready: {e}")
