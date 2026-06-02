# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""NVEIL Visualization Viewer - Main Application Module.

This module contains the main Trame application class and entry point
for the visualization service.
"""
import asyncio
import os
import time
from datetime import datetime, timedelta
from logging import ERROR, WARNING
from multiprocessing.util import INFO
from pathlib import Path
from threading import Lock
from typing import Optional

import i18n
import uvicorn

# Prefer discrete NVIDIA GPU over Intel iGPU (Windows Optimus / hybrid laptops).
# Must be set before any VTK/OpenGL context is created.
if os.name == "nt":
    os.environ.setdefault("SHIM_MCCOMPAT", "0x800000001")

import vtk
import numpy as np
import httpx
# API routes
from api_routes import router as viz_router
from dive.builder.build import switch_timestep
from dive.builder.viz_loader import VizLoader
from construction.load_widgets import build_widget_descriptors
from fastapi import FastAPI
from shared.secrets import get_secret
from shared.service_client import ServiceClient
from helpers import viewer_utils as helper
from logger import *
from trame.app import TrameApp, asynchronous
from trame.decorators import change, controller, life_cycle, trigger
from trame_additionnal_widgets import force_graph
# UI layout builder
from ui import build_main_layout
from ui.icons import MDI
from viz_context import VizContext, StateProxy

from choregraph import Choregraph
from choregraph.viz import KedroVizServer
# from dive import *

logger(service="VIZ", service_id="INIT")

# -- i18n Configuration --
i18n.load_path.append(str(Path(__file__).parent / "locales"))
i18n.set("locale", "en")
i18n.set("fallback", "en")
i18n.set("file_format", "json")
i18n.set("filename_format", "{locale}.{format}")
i18n.set("skip_locale_root_data", True)
# -- END of i18n Configuration --

helper.setup_logging()

# -- Load environment variables --
GCP = get_secret("GCP")
LOCAL = get_secret("LOCAL")
SERVER_HOST = get_secret("SERVER_HOST") or "localhost"
MODULE_PATH = get_secret("MODULE_PATH", "")
KEYFILE_PATH = get_secret("SSL_KEYFILE", "/nveil/backend/ma_cle_privee.key")
CERTFILE_PATH = get_secret("SSL_CERTFILE", "/nveil/backend/mon_certificat.crt")

# -- END of Environment Variables loading --

# Module-level async HTTP client for outbound server_service notifications.
# Reused across every pod-register / viz-ready call so we keep one pool + one
# circuit breaker across the lifetime of the viz process. Per-call retries
# are passed via the `retries=` kwarg on request/post.
_server_client = ServiceClient(verify=True)

# -- Theme Configuration --
# ECharts reads theme tokens inline from ``state.PlotTheme`` — no global
# registration needed after the plotly removal.
# -- END OF Theme Configuration --

# -- FastAPI Application --
api = FastAPI()
api.include_router(viz_router)
# -- END FastAPI Application --


class App(TrameApp):
    """Main Trame application for visualization rendering."""
    
    # Widget state keys that trigger a visualization rebuild on @state.change.
    # Mark-specific keys carry a "<tag>." prefix so different marks never share
    # state; cross-cutting controls (palette, clipping, theme) stay un-prefixed.
    WIDGET_KEYS = [
        # Cross-cutting (un-namespaced — no spec home yet)
        "PlotTheme",
        "FlipPalette", "SelectedPalette", "GlobalIlluminationReach",
        # World-space clipping is NOT in this list — space.clipping.* gets a
        # dedicated lightweight watcher (see _install_clipping_watcher) that
        # re-applies clip planes on the live mapper without rebuilding the
        # voxel pipeline. Slider drags stay interactive that way.
        # Scene-level rendering (persisted to <rendering>)
        "rendering.opacityDensity", "rendering.scatteringBlending",
        "rendering.scatteringAnisotropy", "rendering.graphicalQuality",
        # Per-mark (suffix matches pydantic field name; persisted on the mark)
        "unigrid.resolution", "unigrid.influence", "unigrid.radius",
        "unigrid.clusterReorder",
        "surface.resolution", "surface.influence",
        "contour.resolution", "contour.influence", "contour.delta", "contour.fill",
        "histogram.bins",
        "bar.xOrdering",
        "voxel.windowWidth", "voxel.windowLevel", "voxel.showMPR",
        # Voxel session-only (no persistence — renderer mode toggles)
        "voxel.BlendMode", "voxel.IsoSurfaceValue",
        "point.pointSize", "point.pointOpacity",
        "node.is3D",
        "line.smooth",
        "vector.scale", "vector.use_arrows", "vector.use_streamlines", "vector.useCones",
        "vector.animateFlow", "vector.streamlineDensity", "vector.tubeDiameter",
        "vector.animationSpeed",
        # Vector session-only (perf knob + probe family)
        "vector.VectorSampleCount", "vector.AddProbes",
        "vector.PlaneXYPos", "vector.PlaneXZPos", "vector.PlaneYZPos",
        "vector.ShowPlanePreview",
    ]

    def __init__(self, name=None, cmd_port=None, viz_port=None):
        super().__init__(name=name)
        self.cmd_port = cmd_port
        self.viz_port = viz_port

        # Room state — set by /viz/assign
        self.room_token = None
        self.room_id = None
        self.owner_id = None

        # Pool identity
        self.pool_id = get_secret("POOL_ID", None)
        self.pod_ip = get_secret("POD_IP", "localhost")

        # AFK tracking
        self._last_activity = datetime.now()
        self._activity_lock = Lock()

        self._playback_task = None
        # (kedro state now in self.kedro_manager)

        # -- Trame Server configuration --
        self.server.enable_module(
            {
                "www": f"{MODULE_PATH}/nveil/backend/viz_service/viz_renderer/config/loading",
                "serve": {
                    "viz/config": f"{MODULE_PATH}/nveil/backend/viz_service/viz_renderer/config",
                    "fonts": f"{MODULE_PATH}/nveil/backend/viz_service/viz_renderer/config/fonts",
                },
                "styles": ["viz/config/viz.css"],
            }
        )
        self.server.controller

        force_graph.setup(self.server)

        # Pre-register trame-dockview module so its static assets are
        # available when the server starts (needed for dashboard mode).
        try:
            from trame_dockview import module as dockview_module
            self.server.enable_module(dockview_module)
        except ImportError:
            pass  # trame-dockview not installed — dashboard mode unavailable

        # Register the local trame_echarts module — serves echarts.min.js,
        # echarts-gl.min.js, and the <v-chart> Vue wrapper.
        from trame_echarts import module as trame_echarts_module
        self.server.enable_module(trame_echarts_module)

        limits = httpx.Limits(max_connections=200, max_keepalive_connections=20)
        self.httpx_async_client: httpx.AsyncClient = httpx.AsyncClient(limits=limits, http2=True, verify=True)
        self.server_host = SERVER_HOST

        # -- Mode: "chat" (single viz) or "dashboard" (multi-panel) --
        self.mode = "chat"
        self._building_panels = False  # guard: suppress watchers during panel init

        # -- VizContext registry --
        self.contexts: dict[str, VizContext] = {}
        ctx = VizContext("main")
        self.contexts["main"] = ctx

        # -- Initialize state via context --
        ctx.init_state(self.state)

        # -- VTK Setup (Minimal for UI binding, full setup deferred) --
        ctx.init_vtk()

        # -- Managers --
        from managers.kedro_manager import KedroVizManager
        from managers.history_manager import HistoryManager
        from managers.refresh_manager import URLRefreshManager
        from managers.viz_builder import VizBuilder
        from managers.dashboard_manager import DashboardManager

        self.viz_builder = VizBuilder(
            widget_keys=self.WIDGET_KEYS,
            notify_host_fn=helper.notify_host,
            get_room_token=lambda: self.room_token,
            get_room_id=lambda: self.room_id,
            get_mode=lambda: self.mode,
            get_room_workspace=lambda: self.room_workspace_path,
            server_host=SERVER_HOST,
            is_local=LOCAL == "1",
            state_flush=self.server.state.flush,
            state_dirty=self.server.state.dirty,
        )
        self.kedro_manager = KedroVizManager(
            httpx_client=self.httpx_async_client,
            server_host=SERVER_HOST,
            get_room_token=lambda: self.room_token,
        )
        self.history_manager = HistoryManager(
            build_viz_fn=self.build_viz_for_context,
        )
        self.refresh_manager = URLRefreshManager(
            get_mode=lambda: self.mode,
            get_contexts=lambda: self.contexts,
            get_main_ctx=lambda: self._main_ctx,
            build_viz_fn=self.build_viz_for_context,
            get_last_activity=lambda: self.last_activity,
            notify_host_fn=self._notify_refresh,
        )
        self.dashboard_manager = DashboardManager(
            get_contexts=lambda: self.contexts,
            build_viz_fn=self.build_viz_for_context,
            record_error_fn=self._record_viz_error,
        )

        # -- Context switch lock (serializes /viz/assign requests) --
        self._assign_lock = asyncio.Lock()

        # -- Register widget change watchers for the main context --
        self._register_panel_watchers(ctx)

        # -- Build UI (sets ctrl_* refs on ctx via layout.py) --
        build_main_layout(self)

        # Give the main context a reference to the app controller so that
        # backend fallback paths (ctx.ctrl.figure_update etc.) work.
        ctx.ctrl = self.ctrl

    # -- Backward-compat properties for api_routes.py --

    @property
    def kedro_viz_server(self):
        return self.kedro_manager.kedro_viz_server

    @kedro_viz_server.setter
    def kedro_viz_server(self, value):
        self.kedro_manager.kedro_viz_server = value

    @property
    def _kedro_viz_ready(self):
        return self.kedro_manager._kedro_viz_ready

    @_kedro_viz_ready.setter
    def _kedro_viz_ready(self, value):
        self.kedro_manager._kedro_viz_ready = value

    def update_activity(self):
        """Update the last activity timestamp."""
        with self._activity_lock:
            self._last_activity = datetime.now()

    @property
    def last_activity(self) -> datetime:
        with self._activity_lock:
            return self._last_activity

    @property
    def room_workspace_path(self) -> Optional[Path]:
        """Workspace path for the current room using shared/workspace.py."""
        if self.owner_id and self.room_id:
            from shared.workspace import workspace_path
            return workspace_path(self.owner_id, self.room_id)
        return None

    # ------------------------------------------------------------------
    # Backward-compat properties — delegate to contexts["main"]
    # ------------------------------------------------------------------

    @property
    def _main_ctx(self) -> VizContext:
        return self.contexts["main"]

    @property
    def vl(self):
        return self._main_ctx.vl

    @vl.setter
    def vl(self, value):
        self._main_ctx.vl = value

    @property
    def choregraph(self):
        return self._main_ctx.choregraph

    @choregraph.setter
    def choregraph(self, value):
        self._main_ctx.choregraph = value
        self._main_ctx.vl.choregraph = value

    @property
    def current_xml_path(self):
        return self._main_ctx.current_xml_path

    @current_xml_path.setter
    def current_xml_path(self, value):
        self._main_ctx.current_xml_path = value

    # ------------------------------------------------------------------
    # Dynamic @change watcher registration
    # ------------------------------------------------------------------

    def _register_panel_watchers(self, ctx: VizContext):
        """Register state-change watchers for a panel's widget keys."""
        prefixed_keys = [ctx.state_key(k) for k in self.WIDGET_KEYS]

        @self.state.change(*prefixed_keys)
        def _on_widget_change(**kwargs):
            if self._building_panels or self.mode == "dashboard":
                return
            self.update_activity()
            # Always use the current active context — not the captured `ctx`,
            # which may be stale after a room context switch.
            active_ctx = self.contexts.get("main")
            if (active_ctx
                    and active_ctx.vl.currentFrame is not None
                    and not self.state[active_ctx.state_key("isProcessing")]):
                self.update_viz_for_context(active_ctx, notify=False)

        # --- Clipping watcher (lightweight — reapply on live mapper) ---
        # Full voxel rebuild for every clipping slider tick makes the UI
        # feel laggy (SSAO pass + transfer functions get recreated). Route
        # space.clipping.* through its own handler that just calls
        # apply_clipping on the mapper stashed by vtk_backend.
        clipping_keys = [
            ctx.state_key("space.clipping.mode"),
            ctx.state_key("space.clipping.xPlane"),
            ctx.state_key("space.clipping.yPlane"),
            ctx.state_key("space.clipping.zPlane"),
            ctx.state_key("space.clipping.cameraDepth"),
        ]

        @self.state.change(*clipping_keys)
        def _on_clipping_change(**kwargs):
            if self._building_panels or self.mode == "dashboard":
                return
            active_ctx = self.contexts.get("main")
            if active_ctx is None or active_ctx._vtk_scene is None:
                return
            scene = active_ctx._vtk_scene
            clip = scene.clipping
            if not clip or clip.get("bounds") is None:
                return
            from dive.builder.clipping import apply_clipping, register_camera_clip_observer
            sp = active_ctx.state_proxy
            bounds = clip["bounds"]
            transform = clip["transform"]

            if clip["volume_mappers"]:
                apply_clipping(clip["volume_mappers"], bounds, sp,
                               renderer=scene.renderer, volume=True,
                               transform=transform)
                register_camera_clip_observer(
                    scene.renderer, clip["volume_mappers"], bounds, sp,
                    volume=True, transform=transform,
                )
            if clip["surface_mappers"]:
                apply_clipping(clip["surface_mappers"], bounds, sp,
                               renderer=scene.renderer, volume=False)
                register_camera_clip_observer(
                    scene.renderer, clip["surface_mappers"], bounds, sp,
                    volume=False,
                )

            scene.render()
            if active_ctx.ctrl_view_update:
                try:
                    active_ctx.ctrl_view_update()
                except Exception:
                    pass

        # --- Timeline watchers (separate — timestep switch, not full rebuild) ---

        @self.state.change(ctx.state_key("timeline_current"))
        def _on_timestep_change(**kwargs):
            if self._building_panels or self.mode == "dashboard":
                return
            self.update_activity()
            active_ctx = self.contexts.get("main")
            if not active_ctx or not active_ctx.vl.timestep_index:
                return
            # Skip during initial build — build_viz_for_context sets
            # timeline_current which would trigger a redundant re-render.
            sp = active_ctx.state_proxy
            if sp["isProcessing"]:
                return
            ts_idx = active_ctx.vl.timestep_index
            idx = sp["timeline_current"]
            if idx < 0 or idx >= ts_idx.count:
                return
            value = ts_idx.value_at(idx)
            switch_timestep(active_ctx.vl, value)
            self.update_viz_for_context(active_ctx, notify=False)

        # Flat mirror of voxel.showMPR for Vue's v_show (which can't parse the
        # dot in "voxel.showMPR" as a single identifier). Updating the flat
        # mirror whenever the dotted key changes keeps the layout template
        # Vue-safe without any special-case in the apply/seed pipeline.
        @self.state.change(ctx.state_key("voxel.showMPR"))
        def _on_show_mpr_change(**kwargs):
            active_ctx = self.contexts.get(ctx.panel_id)
            if active_ctx is None:
                return
            sp = active_ctx.state_proxy
            sp["mpr_visible"] = bool(sp.get("voxel.showMPR", False))

        @self.state.change(ctx.state_key("timeline_playing"))
        def _on_playback_toggle(**kwargs):
            active_ctx = self.contexts.get("main")
            if not active_ctx:
                return
            sp = active_ctx.state_proxy
            if sp["timeline_playing"]:
                self._start_playback(active_ctx)
            else:
                self._stop_playback(active_ctx)

        # --- History navigation trigger from React ---
        # React sends the target index; rapid clicks collapse because trame's
        # @state.change only fires on actual value change, so multiple clicks
        # dispatched before historyIndex updates locally all carry the same
        # target and are deduplicated at the trame layer.

        @self.state.change(ctx.state_key("trigger_history_jump"))
        def _on_history_jump(**kwargs):
            active_ctx = self.contexts.get("main")
            if not active_ctx:
                return
            idx = active_ctx.state_proxy["trigger_history_jump"]
            if idx is None or idx < 0:
                return
            self.load_history_viz(idx, active_ctx)

        # --- Probe action triggers from React widgets ---

        @self.state.change(ctx.state_key("trigger_place_probe"))
        def _on_place_probe(**kwargs):
            self.on_place_probe()

        @self.state.change(ctx.state_key("trigger_clear_probes"))
        def _on_clear_probes(**kwargs):
            self.on_clear_probes()

    # ------------------------------------------------------------------
    # Timeline playback
    # ------------------------------------------------------------------

    def _start_playback(self, ctx: VizContext):
        """Start async playback loop for timeline animation."""
        self._stop_playback(ctx)

        async def _loop():
            sp = ctx.state_proxy
            try:
                while sp["timeline_playing"]:
                    fps = max(0.5, sp["timeline_fps"])
                    await asyncio.sleep(1.0 / fps)
                    if not sp["timeline_playing"]:
                        break
                    current = sp["timeline_current"]
                    count = sp["timeline_count"]
                    if count <= 1:
                        break
                    next_idx = (current + 1) % count
                    sp["timeline_current"] = next_idx
                    self.server.state.dirty(ctx.state_key("timeline_current"))
                    self.server.state.flush()
            except Exception as e:
                logger().logp(WARNING, f"Playback loop error: {e}")
            finally:
                sp["timeline_playing"] = False
                self.server.state.dirty(ctx.state_key("timeline_playing"))

        self._playback_task = asyncio.create_task(_loop())

    def _stop_playback(self, ctx: VizContext):
        """Cancel any running playback task."""
        if self._playback_task and not self._playback_task.done():
            self._playback_task.cancel()
            self._playback_task = None

    # -------------------------------------------------------------------------
    # Context Switching (pod-per-user)
    # -------------------------------------------------------------------------

    async def _do_context_switch(self, data: dict):
        """Context switch: teardown old context + start new one.

        Identity (room_id, room_token, owner_id, mode) is already set by
        the /viz/assign handler before this is called.  We only need
        to do the heavy lifting: reset Trame context and kick off
        choregraph + Kedro Viz for the new room.

        For chat→chat switches Kedro Viz is kept alive — run_kedro_viz()
        hot-switches via autoreload instead of a full cold restart.

        Called under _assign_lock — no concurrent switches possible.
        """
        new_mode = data.get("mode", "chat")

        # 1. Cancel refresh task and wait for it to fully stop
        await self._pause_refresh()

        # 2. Only stop Kedro Viz when switching to dashboard mode (doesn't use it).
        #    For chat→chat, run_kedro_viz() will hot-switch via autoreload.
        if new_mode != "chat":
            self._stop_kedro_viz()

        # 3. Tear down old context, create fresh one
        if new_mode == "chat":
            self._reset_chat_context()
        else:
            self._reset_dashboard_context()

        # 4. Initialize the new context
        if new_mode == "chat":
            await self.start_choregraph(self.room_workspace_path)
        else:
            panels_data = data.get("panels", [])
            self.init_dashboard_mode(panels_data)

        logger().logp(INFO, f"Context switch complete → room {self.room_id[:8]}")

    def _carry_over_ui_refs(self, from_ctx: VizContext, to_ctx: VizContext):
        """Transfer UI-bound references (ctrl, VTK) between VizContexts.

        The Trame layout is built once — its widgets (ECharts, VTK RemoteView,
        DeckGL) are bound to specific ctrl functions and a single render_window.
        When switching room contexts, these references must follow the active
        context so that backend renderers can push updates to the UI.

        After this call, *from_ctx* has all transferred attributes set to None,
        making it safe to destroy without freeing shared resources.
        """
        # App controller (fallback for backends)
        to_ctx.ctrl = self.ctrl

        # Per-widget ctrl references (set by layout.py during UI build)
        to_ctx.ctrl_echarts_update = from_ctx.ctrl_echarts_update
        to_ctx.ctrl_echarts_clear = from_ctx.ctrl_echarts_clear
        to_ctx.ctrl_deck_update = from_ctx.ctrl_deck_update
        to_ctx.ctrl_view_update = from_ctx.ctrl_view_update
        to_ctx.ctrl_view_reset_camera = from_ctx.ctrl_view_reset_camera
        from_ctx.ctrl_echarts_update = None
        from_ctx.ctrl_echarts_clear = None
        from_ctx.ctrl_deck_update = None
        from_ctx.ctrl_view_update = None
        from_ctx.ctrl_view_reset_camera = None

        # VTK scene (renderer, window, interactor, MPR — all DOM-bound)
        to_ctx._vtk_scene = from_ctx._vtk_scene
        from_ctx._vtk_scene = None
        # _mpr_ctrl (trame callbacks) transfer separately
        to_ctx._mpr_ctrl = getattr(from_ctx, "_mpr_ctrl", {})
        from_ctx._mpr_ctrl = {}
        # Reset MPR for the incoming room
        if to_ctx._vtk_scene:
            for v in to_ctx._vtk_scene.mpr_views.values():
                v["initialized"] = False
                try:
                    v["renderer"].RemoveAllViewProps()
                except Exception:
                    pass
            to_ctx._vtk_scene._mpr_active = False
            to_ctx._vtk_scene.renderer.RemoveAllViewProps()

    def _reset_chat_context(self):
        """Destroy old chat context, create fresh one, flush stale widget data.

        The Trame layout is built once at startup — we cannot rebuild it.
        Instead we transfer the UI-bound references (ctrl, VTK) to a fresh
        VizContext and explicitly clear all visible widget data so nothing
        from the previous room leaks into the new session.
        """
        current_ctx = self.contexts.get("main")

        new_ctx = VizContext("main")
        new_ctx.init_state(self.state)

        if current_ctx:
            self._carry_over_ui_refs(current_ctx, new_ctx)
            current_ctx.destroy()  # safe — VTK/ctrl refs already nullified
        else:
            new_ctx.init_vtk()
            new_ctx.ctrl = self.ctrl

        self.contexts["main"] = new_ctx

        # Widget controls are now rendered in React (WidgetPanel)

        # Flush state to push all resets (viewer_ready=False, etc.) to frontend
        self.state.flush()

        self._register_panel_watchers(new_ctx)

    def _reset_dashboard_context(self):
        """Destroy old dashboard panel contexts."""
        for pid in list(self.contexts.keys()):
            if pid != "main":
                self.contexts[pid].destroy()
                del self.contexts[pid]

    def release_room(self):
        """Release the current room context without assigning a new one.

        Pod goes to idle state (assigned to user, no active room).
        """
        logger().logp(INFO, f"Releasing room {self.room_id[:8] if self.room_id else '?'}")

        # Note: _pause_refresh() must be awaited by the caller (e.g. /release_room)
        # before calling this sync method, so the refresh loop is already stopped.

        # Stop Kedro Viz
        self._stop_kedro_viz()

        # Destroy current contexts (don't cache — server explicitly released)
        if self.mode == "dashboard":
            for pid, ctx in list(self.contexts.items()):
                if pid != "main":
                    ctx.destroy()
                    del self.contexts[pid]
        else:
            main_ctx = self.contexts.get("main")
            if main_ctx:
                # Re-create a blank main context, transferring UI-bound refs
                new_ctx = VizContext("main")
                new_ctx.init_state(self.state)
                self._carry_over_ui_refs(main_ctx, new_ctx)
                main_ctx.destroy()  # safe — VTK/ctrl refs already nullified
                self.contexts["main"] = new_ctx

        self.room_id = None
        self.room_token = None
        self.mode = "chat"

    def _stop_kedro_viz(self):
        """Stop the Kedro Viz server if running."""
        self.kedro_manager.stop(self.state)

    # -------------------------------------------------------------------------
    # Lifecycle Methods
    # -------------------------------------------------------------------------

    @controller.add("on_server_bind")
    def _bind_middleware(self, wslink_server):
        """Inject caching middleware when the aiohttp server binds."""
        import logging
        from aiohttp import web

        # Suppress noisy aiohttp access logs (static asset requests, .map files, etc.)
        logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

        @web.middleware
        async def cache_control_middleware(request, handler):
            response = await handler(request)
            if request.path.endswith(('.js', '.css', '.woff2', '.ttf', '.png', '.jpg', '.svg', '.wasm')):
                response.headers['Cache-Control'] = 'public, max-age=86400, immutable'
            elif request.path.endswith('.html'):
                response.headers['Cache-Control'] = 'no-cache, must-revalidate'
            return response

        if hasattr(wslink_server, 'app'):
            wslink_server.app.middlewares.insert(0, cache_control_middleware)

    async def run_kedro_viz(self, workspace_path, choregraph_xml_path=None):
        """Start or hot-switch Kedro Viz server. Delegates to KedroVizManager."""
        await self.kedro_manager.run(workspace_path, self.state, choregraph_xml_path)


    # -------------------------------------------------------------------------
    # Dashboard Mode
    # -------------------------------------------------------------------------

    def init_dashboard_mode(self, panels_data: list, **_kwargs):
        """Initialize dashboard mode with multiple panels.

        Layout/Trame glue stays here; panel build logic delegates to DashboardManager.
        """
        from ui.dashboard_layout import build_dashboard_layout, create_panel_template

        self.mode = "dashboard"
        self._building_panels = True
        build_dashboard_layout(self)

        for panel_data in panels_data:
            panel_id = panel_data["panel_id"]
            title = panel_data.get("title", panel_id)
            ws_path = Path(panel_data["workspace_path"]) if panel_data.get("workspace_path") else None

            ctx = VizContext(panel_id, workspace_path=ws_path, title=title)
            self.contexts[panel_id] = ctx
            ctx.init_state(self.state)
            ctx.init_vtk()

            create_panel_template(self, ctx)
            self._register_panel_watchers(ctx)

        self._building_panels = False
        asynchronous.create_task(self._build_and_notify_dashboard())
        logger().logp(INFO, f"Dashboard initialized with {len(panels_data)} panels")

    async def _build_and_notify_dashboard(self):
        """Build all dashboard panels and notify the server when ready."""
        await self.dashboard_manager.build_all_panels()
        await self._notify_viz_ready()

    async def build_all_dashboard_panels(self):
        """Build all dashboard panels sequentially."""
        await self.dashboard_manager.build_all_panels()

    # -------------------------------------------------------------------------
    # Lifecycle Methods
    # -------------------------------------------------------------------------

    @life_cycle.server_ready
    def on_ready(self, **kwargs):
        """Start FastAPI command server and register as available pool pod."""
        asynchronous.create_task(startFastAPI(self.cmd_port))
        asynchronous.create_task(self._register_pool_pod())

    async def _register_pool_pod(self):
        """POST pool_id to /server/port_ready to mark pod available."""
        data = {
            "pool_id": self.pool_id,
            "cmd_port": self.cmd_port,
            "viz_port": self.viz_port,
            "host": self.pod_ip,
        }
        resp = await _server_client.post(
            f"https://{SERVER_HOST}:8000/server/port_ready",
            json=data, timeout=30.0, retries=19,
        )
        if resp.ok:
            logger().logp(INFO, f"Pool pod registered: pool_id={self.pool_id}")
        else:
            logger().logp(ERROR, f"Pool registration failed: {resp.error}")

    async def start_choregraph(self, workspace_path, ctx: Optional[VizContext] = None):
        ctx = ctx or self._main_ctx
        ctx.workspace_path = workspace_path
        cg_path = Path(workspace_path) / "choregraph.xml"

        # Wait for file to appear (max 10s)
        # Useful for guest rooms where files are copied on another pod via NFS
        if GCP == "1":
            for i in range(10):
                if cg_path.exists():
                    break
                logger().logp(DEBUG, f"Waiting for {cg_path.name}... (attempt {i+1}/10)")
                await asyncio.sleep(1)

        xml_arg = str(cg_path) if cg_path.exists() else None

        try:
            ctx.choregraph = Choregraph(xml_spec=xml_arg, workspace_path=workspace_path)
            ctx.vl.choregraph = ctx.choregraph
        except Exception as e:
            logger().logp(ERROR, f"Failed to initialize Choregraph: {e}")

        # Restore last viz state from disk (e.g., after resume from idle)
        spec_path = Path(workspace_path) / "specifications.xml"
        if spec_path.exists() and not ctx.current_xml_path:
            ctx.current_xml_path = str(spec_path)
            self.update_history_list(ctx)

        # Pass choregraph.xml path for label mapping (chat mode only)
        if ctx.panel_id == "main":
            await self.run_kedro_viz(workspace_path, choregraph_xml_path=cg_path if cg_path.exists() else None)

    async def _notify_viz_ready(self):
        """Push readiness to server — triggers viz_ready WS broadcast to frontend."""
        resp = await _server_client.post(
            f"https://{SERVER_HOST}:8000/server/viz_initialized",
            json={"room_token": self.room_token}, timeout=10.0, retries=3,
        )
        if resp.ok:
            logger().logp(INFO, f"Viz ready notification sent for room {self.room_id[:8] if self.room_id else '?'}")
        else:
            logger().logp(WARNING, f"Failed to notify viz readiness: {resp.error}")

    async def _pause_refresh(self) -> Optional[int]:
        """Cancel the refresh loop. Returns saved interval for resume."""
        return await self.refresh_manager.pause()

    def _resume_refresh(self, interval: Optional[int] = None):
        """Restart the refresh loop."""
        self.refresh_manager.resume(interval)

    def set_refresh_interval(self, interval_seconds: Optional[int]):
        """Set or cancel the URL auto-refresh interval."""
        self.refresh_manager.set_interval(interval_seconds)

    async def _notify_refresh(self, total_fetched: int):
        """Callback for URLRefreshManager to notify server of refreshed data."""
        await helper.notify_host(
            SERVER_HOST, self.room_token, "data_refreshed",
            {"source": "auto_refresh", "fetched": total_fetched},
            LOCAL == "1",
        )

    @life_cycle.server_exited
    def notify_server_of_viz_end(self, retries=5, delay=1, **kwargs):
        """Notify the server that the viz has ended.

        Accepts extra kwargs because Trame lifecycle may pass unexpected
        keyword arguments (like `trame__scripts`). Keeps synchronous `requests`
        usage because Trame's server_exited lifecycle doesn't support async.
        """
        import requests

        # Cancel URL refresh scheduler
        if self.refresh_manager._refresh_task is not None:
            self.refresh_manager._refresh_task.cancel()
            self.refresh_manager._refresh_task = None

        # Clean up kedro viz server if running
        if self.kedro_manager.kedro_viz_server is not None:
            try:
                self.kedro_manager.kedro_viz_server.stop()
                logger().logp(INFO, "Kedro Viz server stopped")
            except Exception as e:
                logger().logp(WARNING, f"Failed to stop Kedro Viz server: {e}")

        data = {"room_token": self.room_token, "pool_id": self.pool_id}
        logger().logp(INFO, f"Notifying server of viz end: {data}")
        for attempt in range(retries):
            try:
                response = requests.post(
                    f"https://{SERVER_HOST}:8000/server/handle_pod_exit",
                    json=data,
                    timeout=10,
                    verify=True,
                )
                logger().logp(INFO, f"Room {self.room_token} is powering off")
                return True
            except requests.RequestException as e:
                logger().logp(
                    ERROR,
                    f"Attempt {attempt+1}: Could not notify server of viz end: {e}",
                )
                time.sleep(delay)
        return False

    # -------------------------------------------------------------------------
    # Error Handling
    # -------------------------------------------------------------------------

    def _record_viz_error(self, msg: str, ctx: Optional[VizContext] = None):
        """Record a visualization error in the state and log it."""
        self.viz_builder.record_viz_error(msg, ctx or self._main_ctx)

    # -------------------------------------------------------------------------
    # History Management
    # -------------------------------------------------------------------------

    def update_history_list(self, ctx: Optional[VizContext] = None):
        self.history_manager.update_history_list(ctx or self._main_ctx)

    def load_history_viz(self, index, ctx: Optional[VizContext] = None):
        self.history_manager.load_history_viz(index, ctx or self._main_ctx)

    def previous_viz(self):
        self.history_manager.previous_viz(self._main_ctx)

    def next_viz(self):
        self.history_manager.next_viz(self._main_ctx)

    # -------------------------------------------------------------------------
    # UI Controls
    # -------------------------------------------------------------------------

    def switchNavBar(self):
        """Toggle the navigation bar pin state."""
        sp = self._main_ctx.state_proxy
        sp["pin_widgets_bar"] = not sp["pin_widgets_bar"]
        sp["pin_widgets_bar_icon"] = (
            MDI.DOCK_RIGHT
            if sp["pin_widgets_bar"]
            else MDI.CHEVRON_RIGHT_BOX
        )

    # -------------------------------------------------------------------------
    # Export
    # -------------------------------------------------------------------------

    def export_image(self):
        """Handle export image action with current settings.

        Reads export parameters from Trame state and delegates to
        dive's ``export_image`` which handles backend detection.

        Playwright's sync API cannot run on a thread that already owns
        an asyncio event loop, and trame triggers run inside the server
        loop. We offload the dive export call to a worker thread so the
        loop keeps spinning and the sync_playwright context initializes
        cleanly.
        """
        import concurrent.futures

        from dive.builder.export import export_image as dive_export

        ctx = self._main_ctx
        sp = ctx.state_proxy
        viewer_type = sp["current_viewer_type"]

        if viewer_type == "echarts":
            fig = ctx._last_echarts_option
        else:
            # VTK / DeckGL / graph / html not yet wired through dive_export.
            return None

        if fig is None:
            return None

        extension = sp["export_extension"]
        kwargs = dict(
            fig=fig,
            extension=extension,
            theme=sp["export_theme"],
            transparent=sp["export_transparent"],
            width=int(sp["export_width"]),
            height=int(sp["export_height"]),
            scale=float(sp["export_scale"]),
        )

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            result = ex.submit(dive_export, **kwargs).result()

        if isinstance(result, str):
            result = result.encode("utf-8")
        return self.server.protocol.addAttachment(result)

    @trigger("download_export")
    def trigger_download_export(self):
        """Trigger for downloading the exported image."""
        return self.export_image()

    @trigger("on_viz_click")
    def on_viz_click(self, event_data):
        """Generic click dispatcher: delegates to the handler registered by the active mark."""
        cursor = event_data.get("cursor") if event_data else None
        if cursor:
            logger().logp(DEBUG, f"Viz click cursor: x={cursor.get('x')}, y={cursor.get('y')}")
        logger().logp(DEBUG, f"Viz click event: {event_data}")
        ctx = self._main_ctx
        if ctx.click_handler:
            try:
                ctx.click_handler(ctx, event_data, self.state)
            except Exception as e:
                import traceback
                logger().logp(ERROR, f"VIZ: Click handler error: {e}")
                logger().logp(ERROR, traceback.format_exc())

    @trigger("on_viz_hover")
    def on_viz_hover(self, event_data):
        """Generic hover dispatcher: logs exact cursor coordinates."""
        cursor = event_data.get("cursor") if event_data else None
        ctx = self._main_ctx
        if hasattr(ctx, "hover_handler") and ctx.hover_handler:
            try:
                ctx.hover_handler(ctx, event_data, self.state)
            except Exception as e:
                import traceback
                logger().logp(ERROR, f"VIZ: Hover handler error: {e}")
                logger().logp(ERROR, traceback.format_exc())

    @trigger("vector_field_place_probe")
    def on_place_probe(self):
        """Generic: dispatch probe placement to the active mark's callback."""
        ctx = self._main_ctx
        fn = ctx.mark_callbacks.get("on_place_probe")
        if fn:
            self.viz_builder.clear_cache()
            fn(ctx._vtk_scene, self.state)
            if ctx.ctrl_view_update:
                ctx.ctrl_view_update()

    @trigger("vector_field_planes_start")
    def on_planes_start(self):
        """Show guide planes while a plane slider is actively dragged."""
        self.state["ShowPlanePreview"] = True
        self.update_viz_for_context(self._main_ctx)

    @trigger("vector_field_planes_end")
    def on_planes_end(self):
        """Hide guide planes after slider release."""
        self.state["ShowPlanePreview"] = False
        self.update_viz_for_context(self._main_ctx)

    @trigger("vector_field_clear_probes")
    def on_clear_probes(self):
        """Generic: dispatch probe clearing to the active mark's callback."""
        ctx = self._main_ctx
        fn = ctx.mark_callbacks.get("on_clear_probes")
        if fn:
            self.viz_builder.clear_cache()
            fn(ctx._vtk_scene)
            if ctx.ctrl_view_update:
                ctx.ctrl_view_update()
            self.update_viz_for_context(ctx)

    async def refresh_export_features(self):
        """Refresh export feature availability based on user's license."""
        if not self.owner_id or not self.server_host:
            return

        sp = self._main_ctx.state_proxy
        features = ["png", "jpeg", "svg", "pdf"]

        for feature in features:
            try:
                cookies = {"user_id": self.owner_id, "feature": feature, "value": "true"}
                response = await self.httpx_async_client.get(
                    f"https://{self.server_host}:8000/server/license/feature",
                    cookies=cookies,
                    timeout=5.0
                )
                if response.status_code == 200:
                    res_json = response.json()
                    is_enabled = res_json.get("result", False)
                    sp[f"export_{feature}_disabled"] = not is_enabled
                else:
                    sp[f"export_{feature}_disabled"] = False
            except Exception as e:
                logger().logp(ERROR, f"[Export Features] {feature} check failed: {e}")
                sp[f"export_{feature}_disabled"] = False

        sp.dirty("export_png_disabled", "export_jpeg_disabled",
                 "export_svg_disabled", "export_pdf_disabled")

    # -------------------------------------------------------------------------
    # Visualization Building
    # -------------------------------------------------------------------------

    # NOTE: The static @change decorator is replaced by _register_panel_watchers()
    # called in __init__ for each VizContext. This allows per-panel watchers with
    # prefixed state keys.

    def notify_kedro_viz_update(self, updated=True):
        """Sync config files to the stable wrapper and signal the frontend.

        After a choregraph run, ``_ensure_wrapper()`` rebuilds the room's
        ``pipeline/`` config files (catalog, pipeline_registry, etc.).
        We copy those to the stable wrapper so autoreload detects the change.

        Cache files (``catalogue_stats.json``, run status) are written
        directly by Kedro hooks during execution and are already visible
        to autoreload via the ``cache/`` symlink — no sync needed for those.

        If a reload was triggered, the React postMessage is deferred until
        the Kedro Viz server has finished restarting so the frontend always
        shows the **new** graph rather than the stale one.

        Args:
            updated: If True, indicates the data actually changed.
                    If False, just switches to the pipeline tab.
        """
        reloaded = False
        # Sync room's pipeline config → stable wrapper so autoreload picks it up
        if updated and self.kedro_viz_server and self.kedro_viz_server._stable_wrapper:
            ctx = self._main_ctx
            ws = getattr(ctx, "workspace_path", None) or self.room_workspace_path
            if ws:
                viz_wrapper = Path(ws) / "pipeline"
                if viz_wrapper.exists():
                    self.kedro_viz_server._sync_wrapper(viz_wrapper)
                    self.kedro_viz_server._ready = False
                    self._kedro_viz_ready = False
                    self.kedro_viz_server.trigger_reload()
                    reloaded = True
                    logger().logp(DEBUG, "Stable wrapper synced after choregraph run")

        if reloaded:
            # Defer the postMessage until autoreload completes so the frontend
            # displays the new graph (not the stale one).
            asynchronous.create_task(self._notify_kedro_viz_update_async(updated))
        else:
            # No reload needed — signal immediately (e.g. updated=False)
            self._send_kedro_viz_update_signal(updated)

    async def _notify_kedro_viz_update_async(self, updated=True):
        """Wait for Kedro Viz autoreload to finish, then signal the frontend."""
        if self.kedro_viz_server:
            ready = await self.kedro_viz_server.wait_for_switch(timeout=15.0)
            if ready:
                self._kedro_viz_ready = True
            else:
                logger().logp(WARNING, "Kedro Viz did not become ready within timeout — signalling anyway")
        self._send_kedro_viz_update_signal(updated)

    def _send_kedro_viz_update_signal(self, updated=True):
        """Send the trame-to-react postMessage to tell the iframe to refresh."""
        payload = {
            "emit": "trame-to-react",
            "value": "update-kedro-viz",
            "updated": updated
        }
        if hasattr(self.ctrl, "react_send_event"):
            self.ctrl.react_send_event(payload)
        else:
            logger().logp(WARNING, "react_send_event not available yet")

    def build_viz_from_ui(self, xml_path):
        """Build visualization from an XML specification file (chat mode — main context)."""
        return self.build_viz_for_context(self._main_ctx, xml_path)

    def build_viz_for_context(self, ctx: VizContext, xml_path: str):
        """Build visualization from an XML spec file for a given VizContext."""
        return self.viz_builder.build_viz_for_context(
            ctx, xml_path,
            update_history_fn=self.update_history_list,
            notify_kedro_fn=self.notify_kedro_viz_update,
            build_widget_descriptors_fn=build_widget_descriptors,
        )

    def update_viz_from_ui(self, state, notify=True):
        """Update visualization from current state (chat mode — main context)."""
        return self.update_viz_for_context(self._main_ctx, notify=notify)

    def _widget_state_hash(self, sp) -> int:
        """Compute a hash of current widget state for figure cache keying."""
        return self.viz_builder.widget_state_hash(sp)

    def update_viz_for_context(self, ctx: VizContext, notify=True):
        """Update visualization from current state for a given VizContext."""
        return self.viz_builder.update_viz_for_context(ctx, notify=notify)


# -----------------------------------------------------------------------------
# FastAPI Server
# -----------------------------------------------------------------------------

async def startFastAPI(port: int):
    """Start the FastAPI command server."""
    logger().logp(INFO, f"Starting FastAPI server on port {port}...")
    config = uvicorn.Config(
        api,
        host="0.0.0.0",
        port=port,
        log_level="warning",
        ssl_keyfile=KEYFILE_PATH,
        ssl_certfile=CERTFILE_PATH,
    )
    serverUvicorn = uvicorn.Server(config)
    await serverUvicorn.serve()


# -----------------------------------------------------------------------------
# Entry Point
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    cmd_port = helper.find_available_port(1024)
    viz_port = helper.find_available_port(cmd_port + 1)

    pool_id = get_secret("POOL_ID", "?")
    logger(service="VIZ", service_id=pool_id[:8])
    logger().logp(INFO, f"Starting pool pod: pool_id={pool_id}")

    app = App(cmd_port=cmd_port, viz_port=viz_port)

    api.state.trame_app = app

    app.server.start(
        port=viz_port,
        host="0.0.0.0",
        show_connection_info=False,
        disable_logging=False,
        timeout=0
    )