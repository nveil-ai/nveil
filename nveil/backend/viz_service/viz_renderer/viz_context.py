# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""VizContext — per-panel visualization state container.

Each VizContext encapsulates the complete state for one visualization panel.
In chat mode there is a single context ("main"); in dashboard mode there is
one context per panel ("panel_1", "panel_2", ...).
"""

from pathlib import Path
from typing import Callable, Optional

from dive.builder.viz_loader import VizLoader
from logger import INFO, WARNING, logger
from ui.icons import MDI  # Direct import — avoids ui/__init__.py's heavy layout imports


# ---------------------------------------------------------------------------
# StateProxy — key-prefixing wrapper around trame app.state
# ---------------------------------------------------------------------------

class StateProxy:
    """Transparent proxy around ``app.state`` that auto-prefixes every key.

    Downstream code (frames_to_figures, mark processors, backends) accesses
    ``state["resolution"]`` or ``state.resolution`` as usual — the proxy
    rewrites these to ``"{prefix}resolution"`` on the real state object.
    """

    def __init__(self, state, prefix: str):
        # Use object.__setattr__ to bypass our own __setattr__
        object.__setattr__(self, "_state", state)
        object.__setattr__(self, "_prefix", prefix)

    # ---- dict-style access ----

    def __getitem__(self, key: str):
        return self._state[f"{self._prefix}{key}"]

    def __setitem__(self, key: str, value):
        self._state[f"{self._prefix}{key}"] = value

    def __contains__(self, key: str):
        # try/except instead of ``in`` for the same reason as ``get`` below.
        try:
            self._state[f"{self._prefix}{key}"]
            return True
        except (KeyError, AttributeError, TypeError):
            return False

    def get(self, key: str, default=None):
        """Dict-style get with default — works for dotted keys (e.g. ``unigrid.influence``)
        where attribute-style access can't be used. Treats ``None`` as absent
        because trame's ``state[missing]`` returns ``None`` instead of raising
        ``KeyError``, and widget values are never legitimately ``None``.
        """
        try:
            val = self._state[f"{self._prefix}{key}"]
        except (KeyError, AttributeError, TypeError):
            return default
        return val if val is not None else default

    # ---- attribute-style access ----

    def __getattr__(self, key: str):
        if key.startswith("_"):
            raise AttributeError(key)
        return getattr(self._state, f"{self._prefix}{key}")

    def __setattr__(self, key: str, value):
        if key.startswith("_") or key in ("__class__", "__dict__", "__members__"):
            object.__setattr__(self, key, value)
        else:
            setattr(self._state, f"{self._prefix}{key}", value)

    # ---- context manager (trame batching: ``with state:``) ----

    def __enter__(self):
        return self._state.__enter__()

    def __exit__(self, *args):
        return self._state.__exit__(*args)

    # ---- trame helpers ----

    def dirty(self, *keys: str):
        self._state.dirty(*[f"{self._prefix}{k}" for k in keys])

    def flush(self):
        """Delegate flush to the underlying state."""
        if hasattr(self._state, "flush"):
            self._state.flush()

    @property
    def raw(self):
        """Access the underlying un-prefixed state (escape hatch)."""
        return self._state

    def clear_all(self, default_values: dict):
        """Reset all prefixed keys to their default values.

        Args:
            default_values: dict of {unprefixed_key: default_value} pairs.
        """
        for key, default in default_values.items():
            try:
                self._state[f"{self._prefix}{key}"] = default
            except Exception:
                pass


# ---------------------------------------------------------------------------
# VizContext — per-panel state
# ---------------------------------------------------------------------------

class VizContext:
    """Holds all mutable state for one visualization panel."""

    def __init__(self, panel_id: str, workspace_path: Optional[Path] = None, title: Optional[str] = None):
        self.panel_id = panel_id
        self.title = title or panel_id
        self.workspace_path = workspace_path

        # Reference to the Trame app controller (set by NveilViewer).
        # Used as a fallback by backends when per-widget ctrl_* refs are None.
        self.ctrl = None

        # Viz data loader (project, vs, currentFrame, choregraph reference)
        self.vl = VizLoader()

        # Choregraph instance for this panel
        self.choregraph = None
        self.vl.choregraph = None

        # Path to the current XML specification being displayed
        self.current_xml_path: Optional[str] = None

        # ----- VTK scene (lazy init — only allocated when needed) -----
        self._vtk_scene = None  # dive.builder.vtk.VtkScene

        # ----- Per-panel ctrl references (set when template is created) -----
        self.ctrl_echarts_update: Optional[Callable] = None
        self.ctrl_echarts_clear: Optional[Callable] = None
        self.ctrl_deck_update: Optional[Callable] = None
        self.ctrl_view_update: Optional[Callable] = None
        self.ctrl_view_reset_camera: Optional[Callable] = None

        # ----- Last-rendered echarts option (for export pipeline) -----
        self._last_echarts_option: Optional[dict] = None

        # ----- Click/hover handlers registered by the active mark builder -----
        self.click_handler: Optional[Callable] = None
        self.hover_handler: Optional[Callable] = None
        self.mark_callbacks: dict = {}  # generic mark-specific callbacks (on_place_probe, etc.)

        # ----- StateProxy (set via init_state) -----
        self.state_proxy: Optional[StateProxy] = None

        # ----- History -----
        self.history_files: list = []
        self.current_history_index: int = -1

    # ------------------------------------------------------------------
    # State initialization
    # ------------------------------------------------------------------

    @property
    def prefix(self) -> str:
        """State key prefix. Empty for 'main' (backward compat), '{panel_id}_' otherwise."""
        return "" if self.panel_id == "main" else f"{self.panel_id}_"

    def init_state(self, state):
        """Register all prefixed state keys for this panel on *state*.

        For the ``"main"`` context the prefix is ``""`` (empty) so all
        existing state keys work unchanged.  For dashboard panels the
        prefix is ``"{panel_id}_"``. Dashboard panels read their initial
        widget values from the panel-workspace XML at first render — no
        widget_state dict is injected here.
        """
        p = self.prefix
        self.state_proxy = StateProxy(state, p)

        state[f"{p}pin_widgets_bar"] = True
        state[f"{p}pin_widgets_bar_icon"] = MDI.DOCK_RIGHT
        state[f"{p}vtk_viewer_ready"] = False
        state[f"{p}echarts_viewer_ready"] = False
        state[f"{p}graph_viewer_ready"] = False
        state[f"{p}deckgl_viewer_ready"] = False
        # View-only flat mirror of voxel.showMPR for Vue v_show (which can't parse dots).
        state[f"{p}mpr_visible"] = False
        state[f"{p}deckgl_legend_html"] = ""
        state[f"{p}html_viewer_ready"] = False
        state[f"{p}html_card_groups"] = []
        state[f"{p}use_remote"] = True
        state[f"{p}isProcessing"] = False
        state[f"{p}frame"] = None
        from dive.builder.viz_log import new_viz_log
        state[f"{p}viz_log"] = new_viz_log()
        state[f"{p}viz_error"] = None
        state[f"{p}is_3d"] = False

        # Trigger state
        state[f"{p}trigger_toggle_3d"] = 0
        state[f"{p}trigger_update_data"] = 0
        state[f"{p}trigger_zoom_to_fit"] = 0
        state[f"{p}trigger_focus_on"] = 0
        state[f"{p}trigger_history_jump"] = -1
        state[f"{p}trigger_place_probe"] = 0
        state[f"{p}trigger_clear_probes"] = 0

        # Export dialog state
        state[f"{p}export_theme"] = "dark"
        state[f"{p}export_transparent"] = False
        state[f"{p}export_extension"] = "jpeg"
        state[f"{p}export_width"] = 1200
        state[f"{p}export_height"] = 1200
        state[f"{p}export_scale"] = 1
        state[f"{p}export_theme_items"] = [
            {"title": "Dark", "value": "dark"},
            {"title": "Light", "value": "light"},
        ]
        state[f"{p}current_viewer_type"] = None

        # Plot theme
        state[f"{p}PlotTheme"] = "deep_blue"
        state[f"{p}PlotThemeItems"] = [
            {"title": "Deep Blue", "value": "deep_blue"},
            {"title": "White", "value": "white"},
            {"title": "Paper", "value": "paper"},
            {"title": "Dark", "value": "dark"},
            {"title": "Grey", "value": "grey"},
        ]

        # History
        state[f"{p}history_files"] = []
        state[f"{p}current_history_index"] = -1

        # Kedro Viz (chat-mode only, but always allocate key)
        state[f"{p}kedro_viz_port"] = None

        # Export feature states
        state[f"{p}export_png_disabled"] = False
        state[f"{p}export_jpeg_disabled"] = False
        state[f"{p}export_svg_disabled"] = False
        state[f"{p}export_pdf_disabled"] = False

        # Widget keys — namespaced by mark _tag so different marks don't collide.
        # Cross-cutting controls (palette, clipping, theme) stay un-namespaced.
        # Mark builders read their own state via state.get("<tag>.<key>", default)
        # so missing entries fall back to the descriptor default at render time.
        state[f"{p}space.clipping.mode"] = "axis"
        state[f"{p}space.clipping.xPlane"] = 0.0
        state[f"{p}space.clipping.yPlane"] = 0.0
        state[f"{p}space.clipping.zPlane"] = 0.0
        state[f"{p}space.clipping.cameraDepth"] = 0.0
        state[f"{p}FlipPalette"] = False
        state[f"{p}SelectedPalette"] = "current"
        state[f"{p}GlobalIlluminationReach"] = 0.0
        state[f"{p}graph_data"] = None
        state[f"{p}widget_descriptors"] = "[]"

        # Timeline state
        state[f"{p}timeline_visible"] = False
        state[f"{p}timeline_count"] = 0
        state[f"{p}timeline_current"] = 0
        state[f"{p}timeline_values"] = []
        state[f"{p}timeline_labels"] = []
        state[f"{p}timeline_playing"] = False
        state[f"{p}timeline_fps"] = 2

    # ------------------------------------------------------------------
    # VTK lazy initialization
    # ------------------------------------------------------------------

    def init_vtk(self):
        """Create VTK scene (renderer / window / interactor / MPR) for this panel.

        Call this lazily — only when a VTK-type visualization is needed.
        MPR render windows are created eagerly because the trame layout
        binds VtkRemoteView at template-build time.
        """
        if self._vtk_scene is not None:
            return
        from dive.builder.vtk import VtkScene
        self._vtk_scene = VtkScene.create(offscreen=True, trackball=True, mpr=True)

    # ------------------------------------------------------------------
    # State defaults (used by destroy / clear_all)
    # ------------------------------------------------------------------

    STATE_DEFAULTS = {
        "pin_widgets_bar": True,
        "pin_widgets_bar_icon": MDI.DOCK_RIGHT,
        "vtk_viewer_ready": False,
        "echarts_viewer_ready": False,
        "graph_viewer_ready": False,
        "deckgl_viewer_ready": False,
        "mpr_visible": False,
        "deckgl_legend_html": "",
        "html_viewer_ready": False,
        "html_card_groups": [],
        "use_remote": True,
        "isProcessing": False,
        "frame": None,
        "viz_log": {},
        "viz_error": None,
        "is_3d": False,
        "trigger_toggle_3d": 0,
        "trigger_update_data": 0,
        "trigger_zoom_to_fit": 0,
        "trigger_focus_on": 0,
        "trigger_history_jump": -1,
        "trigger_place_probe": 0,
        "trigger_clear_probes": 0,
        "export_theme": "dark",
        "export_transparent": False,
        "export_extension": "jpeg",
        "export_width": 1200,
        "export_height": 1200,
        "export_scale": 1,
        "export_theme_items": [
            {"title": "Dark", "value": "dark"},
            {"title": "Light", "value": "light"},
        ],
        "current_viewer_type": None,
        "history_files": [],
        "current_history_index": -1,
        "kedro_viz_port": None,
        "export_png_disabled": False,
        "export_jpeg_disabled": False,
        "export_svg_disabled": False,
        "export_pdf_disabled": False,
        "PlotTheme": "deep_blue",
        "PlotThemeItems": [
            {"title": "Deep Blue", "value": "deep_blue"},
            {"title": "White", "value": "white"},
            {"title": "Paper", "value": "paper"},
            {"title": "Dark", "value": "dark"},
            {"title": "Grey", "value": "grey"},
        ],
        "space.clipping.mode": "axis",
        "space.clipping.xPlane": 0.0,
        "space.clipping.yPlane": 0.0,
        "space.clipping.zPlane": 0.0,
        "space.clipping.cameraDepth": 0.0,
        "FlipPalette": False,
        "SelectedPalette": "current",
        "GlobalIlluminationReach": 0.0,
        "graph_data": None,
        "timeline_visible": False,
        "timeline_count": 0,
        "timeline_current": 0,
        "timeline_values": [],
        "timeline_labels": [],
        "timeline_playing": False,
        "timeline_fps": 2,
    }

    # ------------------------------------------------------------------
    # Destroy / cleanup
    # ------------------------------------------------------------------

    def destroy(self):
        """Full cleanup of this VizContext — free VTK resources, Choregraph,
        and reset all prefixed state keys to defaults."""
        logger().logp(INFO, f"Destroying VizContext '{self.panel_id}'")

        # 1. VTK cleanup
        try:
            if self._vtk_scene:
                self._vtk_scene.destroy()
        except Exception as e:
            logger().logp(WARNING, f"VTK cleanup error for '{self.panel_id}': {e}")
        self._vtk_scene = None

        # 2. Choregraph cleanup (release in-memory caches only, keep disk files)
        if self.choregraph:
            try:
                self.choregraph.close()
            except Exception:
                pass
            self.choregraph = None
        if self.vl:
            self.vl.choregraph = None
            self.vl.currentFrame = None
            self.vl.project = None

        # 3. Clear all prefixed state keys to defaults
        if self.state_proxy:
            self.state_proxy.clear_all(self.STATE_DEFAULTS)

        # 4. Clear ctrl references
        self._last_echarts_option = None
        self.ctrl_echarts_update = None
        self.ctrl_echarts_clear = None
        self.ctrl_deck_update = None
        self.ctrl_view_update = None
        self.ctrl_view_reset_camera = None
        self.click_handler = None
        self.hover_handler = None

        # 5. Reset instance state
        self.current_xml_path = None
        self.workspace_path = None
        self.history_files = []
        self.current_history_index = -1

        logger().logp(INFO, f"VizContext '{self.panel_id}' destroyed")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def state_key(self, key: str) -> str:
        """Return the prefixed state key name."""
        return f"{self.prefix}{key}"
