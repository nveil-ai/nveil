# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Visualization building — frame creation, caching, backend dispatch."""

import asyncio
import collections
from logging import ERROR, WARNING
from typing import Callable, List, Optional

from logger import INFO, DEBUG, logger


class VizBuilder:
    """Builds and updates visualizations for VizContexts.

    Manages the figure cache (keyed by timestep + widget hash) and dispatches
    rendered objects to the correct backend (ECharts, VTK, DeckGL, Graph, HTML).

    Args:
        widget_keys: List of state keys that affect rendering (for hashing).
        notify_host_fn: Async callback ``(room_token, event, data, local) -> None``.
        get_room_token: Callable returning the current room token.
        get_room_id: Callable returning the current room_id.
        get_mode: Callable returning the current mode ("chat" or "dashboard").
        get_room_workspace: Callable returning Optional[Path] for workspace.
        server_host: Server hostname for notifications.
        is_local: Whether running in local mode.
        state_flush: Callable to flush trame state.
        state_dirty: Callable to dirty specific state keys.
    """

    def __init__(
        self,
        widget_keys: List[str],
        notify_host_fn: Callable,
        get_room_token: Callable,
        get_room_id: Callable,
        get_mode: Callable,
        get_room_workspace: Callable,
        server_host: str,
        is_local: bool,
        state_flush: Callable,
        state_dirty: Callable,
    ):
        self._widget_keys = widget_keys
        self._notify_host = notify_host_fn
        self._get_room_token = get_room_token
        self._get_room_id = get_room_id
        self._get_mode = get_mode
        self._get_room_workspace = get_room_workspace
        self._server_host = server_host
        self._is_local = is_local
        self._state_flush = state_flush
        self._state_dirty = state_dirty

        # Figure cache: (timestep_value, widget_hash) → (vizObjects, axes, scalar_bars, objectTypes, click_handlers)
        self._figure_cache: collections.OrderedDict[tuple, tuple] = collections.OrderedDict()
        self._figure_cache_max = 10

    def _fire_thumbnail_capture(self, fig, viz_file: str, theme: str = "dark"):
        """Best-effort async thumbnail via dive_export. Fire-and-forget.

        Skips regeneration when the PNG already exists and is at least as
        fresh as the spec file — history navigation re-runs the full build
        path for determinism, but the thumbnail hasn't changed since the
        spec hasn't changed. Spec edits (widget-state bakes, AI rewrites)
        bump the spec mtime and re-trigger capture naturally.
        """
        from pathlib import Path

        ws = self._get_room_workspace()
        if not ws or not viz_file:
            return

        out_path = ws / "artifacts" / (Path(viz_file).stem + ".png")

        try:
            spec_mtime = Path(viz_file).stat().st_mtime
            if out_path.exists() and out_path.stat().st_mtime >= spec_mtime:
                return
        except OSError:
            pass

        is_vtk = isinstance(fig, dict) and ("mapper" in fig or "volume" in fig)
        # Text/KPI cards are list[{"cards": ...}] — transparent captures would
        # erase the theme-tinted card surface, so opt them into an opaque PNG.
        is_html_backend = (
            isinstance(fig, list) and fig
            and isinstance(fig[0], dict) and "cards" in fig[0]
        )
        transparent = not is_html_backend

        async def _capture():
            try:
                from dive.builder.export import export_image as dive_export
                out_path.parent.mkdir(parents=True, exist_ok=True)
                if is_vtk:
                    # VTK objects carry OpenGL state bound to the creating
                    # thread — run synchronously (offscreen render is ~200ms).
                    png_bytes = dive_export(
                        fig, extension="png", theme=theme, transparent=transparent,
                        width=400, height=300, scale=0.5,
                    )
                else:
                    png_bytes = await asyncio.to_thread(
                        dive_export, fig,
                        extension="png", theme=theme, transparent=transparent,
                        width=400, height=300, scale=0.5,
                    )
                if isinstance(png_bytes, bytes):
                    out_path.write_bytes(png_bytes)
            except Exception as e:
                logger().logp(WARNING, f"Thumbnail capture failed for {viz_file}: {e}")

        asyncio.create_task(_capture())

    def clear_cache(self):
        """Clear the figure cache."""
        self._figure_cache.clear()

    def widget_state_hash(self, sp) -> int:
        """Compute a hash of current widget state for figure cache keying."""
        vals = []
        for k in self._widget_keys:
            try:
                vals.append(sp[k])
            except Exception:
                vals.append(None)
        # Include probe count so the cache is invalidated when probes are added/removed
        # (__vf_2d_probes bypasses WIDGET_KEYS watchers — updated directly by the click handler)
        try:
            probes = sp["__vf_2d_probes"]
            vals.append(len(probes) if probes else 0)
        except Exception:
            pass
        return hash(tuple(str(v) for v in vals))

    def record_viz_error(self, msg: str, ctx) -> None:
        """Record a visualization error in the state and log it."""
        from dive.builder.viz_log import ensure_viz_log
        sp = ctx.state_proxy
        try:
            viz_log = ensure_viz_log(sp)
            viz_log["errors"].append(msg)
            sp["viz_log"] = viz_log  # re-assign to trigger Trame state notifications
            sp["viz_error"] = msg
        except Exception as e:
            logger().logp(ERROR, f"Failed to record viz error: {e}")
        logger().logp(ERROR, msg)

    def build_viz_for_context(
        self,
        ctx,
        xml_path: str,
        *,
        update_history_fn: Optional[Callable] = None,
        notify_kedro_fn: Optional[Callable] = None,
        build_widget_descriptors_fn: Optional[Callable] = None,
    ):
        """Build visualization from an XML spec file for a given VizContext.

        Args:
            ctx: VizContext to build for.
            xml_path: Path to the XML spec file.
            update_history_fn: Callback to update history list after build.
            notify_kedro_fn: Callback to notify Kedro Viz of update.
            build_widget_descriptors_fn: Callback to build widget descriptors.

        Returns:
            Generated file path if build succeeds with history, else None.
        """
        from pathlib import Path
        from helpers import viewer_utils as helper
        from dive.builder.build import build_with_history, get_timeline_info

        self.clear_cache()

        # Signal the echarts widget that the next option push starts a fresh
        # chart — new chat plot or history click both land here. The Vue
        # watcher calls ``chart.clear()`` before setOption so stale series /
        # visualMap / formatters from the previous chart are wiped. Widget
        # updates (slider drags, theme flips) go through update_viz_for_context
        # directly and do NOT bump the counter, so they still merge and
        # preserve 3D camera state.
        if ctx.ctrl_echarts_clear is not None:
            try:
                ctx.ctrl_echarts_clear()
            except Exception as e:
                logger().logp(WARNING, f"ctrl_echarts_clear failed: {e}")

        sp = ctx.state_proxy

        # Reconstruct path if it's just a filename
        if "/" not in xml_path and "\\" not in xml_path:
            ws = ctx.workspace_path or self._get_room_workspace()
            if ws:
                xml_path = str(ws / xml_path)
            else:
                logger().logp(ERROR, f"Room not assigned, cannot reconstruct path for filename: {xml_path}")

        # Guard: reject paths from a different room (stale command after context switch)
        room_id = self._get_room_id()
        if room_id and "/" in xml_path and self._get_mode() != "dashboard":
            path_parts = Path(xml_path).parts
            if "DIVE" in path_parts and room_id not in xml_path:
                logger().logp(WARNING, f"Skipping stale xml_path from a different room: {xml_path}")
                return None

        ctx.current_xml_path = xml_path
        if ctx._vtk_scene is not None:
            ctx._vtk_scene._camera_initialized = False
        sp["isProcessing"] = True
        from dive.builder.viz_log import new_viz_log
        sp["viz_log"] = new_viz_log()
        sp["viz_error"] = None
        sp["widget_descriptors"] = "[]"
        self._state_dirty(ctx.state_key("isProcessing"))
        system_message = "Visualization specification file does not exist."
        generated_file = None

        if helper.file_exists(xml_path):
            def extract_owner_and_room_id(p):
                parts = Path(p).parts
                for i, part in enumerate(parts):
                    if part == "DIVE" and i + 2 < len(parts):
                        return parts[i + 1], parts[i + 2]
                return None, None

            owner_id, room_id_parsed = extract_owner_and_room_id(xml_path)

            try:
                success, system_message, notify_error, generated_file = build_with_history(
                    ctx.vl, xml_path, room_id_parsed, owner_id,
                )
            except Exception as e:
                self.record_viz_error(f"Frame preparation failed: {e}", ctx)
                success, system_message, notify_error, generated_file = False, str(e), True, None

            if success:
                if generated_file:
                    ctx.current_xml_path = generated_file

                if ctx.vl.choregraph:
                    ctx.choregraph = ctx.vl.choregraph

                # History file → choregraph was restored, refresh Kedro Viz pipeline
                if "specificationsEnhanced_" in xml_path and ctx.vl.choregraph:
                    try:
                        ctx.vl.choregraph._catalog_instance = None
                        ctx.vl.choregraph._ensure_wrapper()
                        if notify_kedro_fn:
                            notify_kedro_fn(updated=True)
                    except Exception as e:
                        logger().logp(WARNING, f"Failed to refresh Kedro Viz after history switch: {e}")

                # Build widget descriptors AND seed state from their mark-derived
                # defaults. Runs for every panel (main + dashboard) so the render
                # path always finds the XML values in state — no per-panel fallback
                # logic in mark builders. Dashboards just don't display the widget
                # bar on the frontend, so the descriptor JSON they receive is
                # harmless dead state.
                if build_widget_descriptors_fn:
                    import traceback as _tb
                    import os as _os
                    _dev = _os.getenv("LOCAL", "0") == "1"
                    try:
                        if _dev:
                            mark_types = [type(getattr(mf, "mark", None)).__name__ for mf in (ctx.vl.currentFrame or [])]
                            logger().logp(INFO, f"[WIDGETS] Building descriptors for {ctx.panel_id} mark types: {mark_types}")
                        desc_json = build_widget_descriptors_fn(sp, ctx.vl)
                        if _dev:
                            logger().logp(INFO, f"[WIDGETS] desc_json ({len(desc_json)} chars): {desc_json[:300]}")
                        sp["widget_descriptors"] = desc_json
                    except Exception as e:
                        logger().logp(WARNING, f"[WIDGETS] Widget descriptors failed: {e}\n{_tb.format_exc()}")

                # Populate timeline state from dive's API
                info = get_timeline_info(ctx.vl)
                if info:
                    safe_values = [
                        v.isoformat() if hasattr(v, 'isoformat') else float(v) if hasattr(v, '__float__') else v
                        for v in info["values"]
                    ]
                    sp["timeline_visible"] = True
                    sp["timeline_count"] = int(info["count"])
                    sp["timeline_values"] = safe_values
                    sp["timeline_labels"] = [str(l) for l in info["labels"]]
                    sp["timeline_current"] = 0
                    sp["timeline_playing"] = False
                else:
                    sp["timeline_visible"] = False
                    sp["timeline_count"] = 0

                if update_history_fn:
                    update_history_fn(ctx)
                from dive.builder.viz_log import ensure_viz_log
                viz_log = ensure_viz_log(sp)
                if system_message:
                    viz_log["messages"].append(system_message)
                sp["viz_log"] = viz_log

                try:
                    self.update_viz_for_context(ctx)
                except Exception as e:
                    if not sp["viz_error"]:
                        self.record_viz_error(f"Visualization update failed: {e}", ctx)

            else:
                self.record_viz_error(system_message, ctx)
                if notify_error:
                    asyncio.create_task(
                        self._notify_host(
                            self._server_host, self._get_room_token(), "error",
                            {"error": system_message, "notify_error": notify_error},
                            self._is_local,
                        )
                    )
        else:
            self.record_viz_error(system_message, ctx)
            logger().logp(ERROR, f"File {xml_path} does not exist.")

        sp["isProcessing"] = False
        self._state_dirty(ctx.state_key("isProcessing"))
        self._state_flush()

        return generated_file if 'success' in locals() and success else None

    def update_viz_for_context(self, ctx, notify=True):
        """Update visualization from current state for a given VizContext.

        Returns True if rendering succeeded, False otherwise.
        """
        from helpers import viewer_utils as helper
        from dive.builder.build import frames_to_figures
        from backends import (
            show_deckgl_viz, show_echarts_viz, show_graph_viz,
            show_html_viz, show_vtk_viz,
        )

        sp = ctx.state_proxy

        # Ensure VTK renderer exists for this context
        if ctx._vtk_scene is None:
            ctx.init_vtk()

        if not ctx.vl.currentFrame:
            logger().logp(WARNING, "update_viz_for_context: currentFrame is None or empty — skipping render")
            return False

        # Figure cache: skip frames_to_figures if same (timestep, widgets)
        ts_value = None
        if ctx.vl.currentFrame:
            ts_value = getattr(ctx.vl.currentFrame[0], 'timestep', None) if ctx.vl.currentFrame else None
        cache_key = (ts_value, self.widget_state_hash(sp))
        cached_fig = self._figure_cache.get(cache_key)

        try:
            if cached_fig is not None:
                vizObjects, axes, scalar_bars, objectTypes, click_handlers, hover_handlers = cached_fig
            else:
                vizObjects, axes, scalar_bars, objectTypes, click_handlers, hover_handlers = frames_to_figures(
                    ctx.vl.currentFrame, sp, ctx._vtk_scene.renderer
                )
                self._figure_cache[cache_key] = (vizObjects, axes, scalar_bars, objectTypes, click_handlers, hover_handlers)
                self._figure_cache.move_to_end(cache_key)
                while len(self._figure_cache) > self._figure_cache_max:
                    self._figure_cache.popitem(last=False)
        except Exception as e:
            self.record_viz_error(f"frames_to_figures failed: {e}", ctx)
            if notify:
                asyncio.create_task(
                    self._notify_host(
                        self._server_host, self._get_room_token(), "error",
                        {"error": f"viz generation failed: {e}"},
                        self._is_local,
                    )
                )
            return False

        viewer_keys = [
            "graph_viewer_ready", "vtk_viewer_ready",
            "echarts_viewer_ready",
            "deckgl_viewer_ready", "html_viewer_ready",
            "current_viewer_type",
        ]

        def _set_viewer_state(active_type: str):
            """Set one viewer ready, rest off."""
            type_map = {
                "deckgl": "deckgl_viewer_ready",
                "vtk": "vtk_viewer_ready",
                "html": "html_viewer_ready",
                "echarts": "echarts_viewer_ready",
                "graph": "graph_viewer_ready",
            }
            for key in type_map.values():
                sp[key] = False
            sp[type_map[active_type]] = True
            sp["current_viewer_type"] = active_type
            if active_type != "deckgl":
                ctx._deckgl_view_initialized = False
                # Clear DeckGL layers to free GPU buffers while hidden
                if hasattr(ctx, "ctrl_deck_update") and ctx.ctrl_deck_update:
                    try:
                        import pydeck as pdk
                        ctx.ctrl_deck_update(pdk.Deck(layers=[]))
                    except Exception:
                        pass
            self._state_dirty(*[ctx.state_key(k) for k in viewer_keys])

        success = False
        try:
            if "map" in objectTypes:
                success = True
                _set_viewer_state("deckgl")
                deck_title = ""
                deck_desc = ""
                if ctx.vl.currentFrame:
                    first_frame = ctx.vl.currentFrame[0] if isinstance(ctx.vl.currentFrame, list) else ctx.vl.currentFrame
                    deck_title = getattr(first_frame, "figureTitle", "")
                    deck_desc = getattr(first_frame, "figureDescription", "")
                show_deckgl_viz(ctx, vizObjects, figure_title=deck_title, figure_description=deck_desc)

            elif "vtk" in objectTypes:
                success = True
                _set_viewer_state("vtk")
                figure_title = ""
                if ctx.vl.currentFrame:
                    first_frame = ctx.vl.currentFrame[0] if isinstance(ctx.vl.currentFrame, list) else ctx.vl.currentFrame
                    figure_title = getattr(first_frame, "figureTitle", "")
                show_vtk_viz(ctx, vizObjects, axes, scalar_bars, figure_title=figure_title)

            elif "html" in objectTypes:
                logger().logp(INFO, "HTML object detected, showing HTML card visualization")
                success = True
                _set_viewer_state("html")
                html_title = ""
                if ctx.vl.currentFrame:
                    first_frame = ctx.vl.currentFrame[0] if isinstance(ctx.vl.currentFrame, list) else ctx.vl.currentFrame
                    html_title = getattr(first_frame, "figureTitle", "")
                show_html_viz(ctx, vizObjects[0] if vizObjects else [], figure_title=html_title)

            elif "echarts" in objectTypes:
                success = True
                _set_viewer_state("echarts")
                first_frame = ctx.vl.currentFrame[0] if isinstance(ctx.vl.currentFrame, list) else ctx.vl.currentFrame
                show_echarts_viz(ctx, vizObjects, frame=first_frame)

            elif "graph" in objectTypes:
                logger().logp(INFO, "Graph object detected, showing Graph visualization")
                success = True
                _set_viewer_state("graph")
                show_graph_viz(ctx, vizObjects)

            else:
                success = False
                detail = f"objectTypes={objectTypes}" if objectTypes else "objectTypes=[] (all marks may have been skipped — check chosen_backend vs mark backends)"
                self.record_viz_error(f"No recognizable visualization object types produced. {detail}", ctx)

        except Exception as e:
            self.record_viz_error(f"Rendering failed: {e}", ctx)
            success = False

        if success:
            sp["viz_error"] = None
            # Register click handler from the last mark that provided one
            ctx.click_handler = click_handlers[-1] if click_handlers else None
            ctx.hover_handler = hover_handlers[-1] if hover_handlers else None
            # Extract mark-specific callbacks from VTK viz objects
            ctx.mark_callbacks = {}
            for obj in vizObjects:
                if isinstance(obj, dict):
                    for cb_key in ("on_place_probe", "on_clear_probes", "on_render"):
                        fn = obj.get(cb_key)
                        if callable(fn):
                            ctx.mark_callbacks[cb_key] = fn

            if notify:
                viewer = sp["current_viewer_type"]
                if viewer == "echarts" and ctx._last_echarts_option:
                    fig = ctx._last_echarts_option
                else:
                    fig = vizObjects[0] if vizObjects else None
                if fig:
                    try:
                        theme = sp["PlotTheme"] or "dark"
                    except Exception:
                        theme = "dark"
                    self._fire_thumbnail_capture(fig, ctx.current_xml_path, theme=theme)
        else:
            ctx.click_handler = None
            ctx.hover_handler = None
            ctx.mark_callbacks = {}

        self._state_flush()

        if notify:
            payload = {}
            if success:
                try:
                    wd = sp["widget_descriptors"]
                    if wd and wd != "[]":
                        payload["widget_descriptors"] = wd
                except Exception:
                    pass
            else:
                payload = {"error": "viz generation failed. See viz_log."}
            asyncio.create_task(
                self._notify_host(
                    self._server_host, self._get_room_token(),
                    "viz_loaded" if success else "error",
                    payload,
                    self._is_local,
                )
            )
        return success
