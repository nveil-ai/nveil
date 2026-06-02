# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for VizContext — per-panel state container with real VTK objects."""

import pytest
from pathlib import Path

vtk = pytest.importorskip("vtk", reason="vtk not installed")
from viz_context import VizContext


class TestPrefix:
    def test_main_panel_empty_prefix(self):
        ctx = VizContext("main")
        assert ctx.prefix == ""

    def test_dashboard_panel_prefixed(self):
        ctx = VizContext("panel_1")
        assert ctx.prefix == "panel_1_"

    def test_state_key_main(self):
        ctx = VizContext("main")
        assert f"{ctx.prefix}resolution" == "resolution"

    def test_state_key_dashboard(self):
        ctx = VizContext("panel_2")
        assert f"{ctx.prefix}resolution" == "panel_2_resolution"


class TestConstructor:
    def test_creates_viz_loader(self):
        ctx = VizContext("main")
        assert ctx.vl is not None

    def test_workspace_path_stored(self):
        p = Path("/tmp/test")
        ctx = VizContext("main", workspace_path=p)
        assert ctx.workspace_path == p

    def test_title_defaults_to_panel_id(self):
        ctx = VizContext("my_panel")
        assert ctx.title == "my_panel"

    def test_title_override(self):
        ctx = VizContext("my_panel", title="Custom Title")
        assert ctx.title == "Custom Title"

    def test_history_defaults(self):
        ctx = VizContext("main")
        assert ctx.history_files == []
        assert ctx.current_history_index == -1


class TestVTKInit:
    def test_creates_real_renderer(self):
        ctx = VizContext("main")
        ctx.init_vtk()
        assert isinstance(ctx._vtk_scene.renderer, vtk.vtkRenderer)

    def test_creates_render_window(self):
        ctx = VizContext("main")
        ctx.init_vtk()
        assert isinstance(ctx._vtk_scene.render_window, vtk.vtkRenderWindow)

    def test_creates_interactor(self):
        ctx = VizContext("main")
        ctx.init_vtk()
        assert isinstance(ctx._vtk_scene.interactor, vtk.vtkRenderWindowInteractor)

    def test_offscreen_rendering_enabled(self):
        ctx = VizContext("main")
        ctx.init_vtk()
        assert ctx._vtk_scene.render_window.GetOffScreenRendering() == 1

    def test_idempotent(self):
        ctx = VizContext("main")
        ctx.init_vtk()
        r1 = ctx._vtk_scene.renderer
        ctx.init_vtk()  # second call should be a no-op
        assert ctx._vtk_scene.renderer is r1


class TestStateDefaults:
    def test_has_expected_keys(self):
        defaults = VizContext.STATE_DEFAULTS
        # Cross-cutting controls live in STATE_DEFAULTS; per-mark widget keys
        # are namespaced (e.g. "unigrid.resolution") and seeded dynamically
        # by build_widget_descriptors at viz-load time, not here.
        assert "PlotTheme" in defaults
        assert "timeline_visible" in defaults
        assert "export_extension" in defaults
        assert "space.clipping.mode" in defaults

    def test_clip_mode_default(self):
        assert VizContext.STATE_DEFAULTS["space.clipping.mode"] == "axis"

    def test_timeline_defaults(self):
        assert VizContext.STATE_DEFAULTS["timeline_visible"] is False
        assert VizContext.STATE_DEFAULTS["timeline_count"] == 0
