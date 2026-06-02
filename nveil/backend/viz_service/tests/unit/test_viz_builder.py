# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for VizBuilder — caching, hashing, error recording, backend dispatch."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from managers.viz_builder import VizBuilder

WIDGET_KEYS = ["PlotTheme", "resolution", "bins"]


def _make_builder(**overrides):
    """Create a VizBuilder with safe defaults."""
    defaults = dict(
        widget_keys=WIDGET_KEYS,
        notify_host_fn=AsyncMock(),
        get_room_token=lambda: "tok",
        get_room_id=lambda: "room1",
        get_mode=lambda: "chat",
        get_room_workspace=lambda: None,
        server_host="localhost",
        is_local=True,
        state_flush=MagicMock(),
        state_dirty=MagicMock(),
    )
    defaults.update(overrides)
    return VizBuilder(**defaults)


class _FakeStateProxy(dict):
    """Dict-based state proxy for testing."""
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)


def _make_ctx(panel_id="main"):
    """Create a minimal fake VizContext."""
    ctx = MagicMock()
    ctx.panel_id = panel_id
    ctx.state_proxy = _FakeStateProxy({
        "viz_log": {"errors": [], "warnings": [], "messages": [], "frames": []},
        "viz_error": None,
        "isProcessing": False,
        "PlotTheme": "dark",
        "resolution": 30,
        "bins": 10,
    })
    ctx.state_key = lambda k: f"main_{k}"
    return ctx


class TestWidgetStateHash:
    def test_same_state_same_hash(self):
        builder = _make_builder()
        sp = _FakeStateProxy({"PlotTheme": "dark", "resolution": 30, "bins": 10})
        h1 = builder.widget_state_hash(sp)
        h2 = builder.widget_state_hash(sp)
        assert h1 == h2

    def test_different_state_different_hash(self):
        builder = _make_builder()
        sp1 = _FakeStateProxy({"PlotTheme": "dark", "resolution": 30, "bins": 10})
        sp2 = _FakeStateProxy({"PlotTheme": "light", "resolution": 30, "bins": 10})
        h1 = builder.widget_state_hash(sp1)
        h2 = builder.widget_state_hash(sp2)
        assert h1 != h2

    def test_missing_keys_handled(self):
        builder = _make_builder()
        sp = _FakeStateProxy({})  # no keys at all
        h = builder.widget_state_hash(sp)
        assert isinstance(h, int)

    def test_hash_is_int(self):
        builder = _make_builder()
        sp = _FakeStateProxy({"PlotTheme": "x", "resolution": 1, "bins": 2})
        assert isinstance(builder.widget_state_hash(sp), int)


class TestFigureCache:
    def test_clear_cache(self):
        builder = _make_builder()
        builder._figure_cache[(None, 123)] = ("a", "b", "c", "d")
        assert len(builder._figure_cache) == 1
        builder.clear_cache()
        assert len(builder._figure_cache) == 0

    def test_cache_eviction(self):
        builder = _make_builder()
        builder._figure_cache_max = 3
        for i in range(5):
            builder._figure_cache[(i, 0)] = (f"obj{i}",)
            builder._figure_cache.move_to_end((i, 0))
            while len(builder._figure_cache) > builder._figure_cache_max:
                builder._figure_cache.popitem(last=False)
        assert len(builder._figure_cache) == 3
        # Oldest entries (0, 1) should be evicted
        assert (0, 0) not in builder._figure_cache
        assert (1, 0) not in builder._figure_cache
        assert (4, 0) in builder._figure_cache

    def test_cache_hit_returns_same(self):
        builder = _make_builder()
        expected = (["obj"], ["ax"], ["sb"], {"echarts"})
        builder._figure_cache[(None, 42)] = expected
        result = builder._figure_cache.get((None, 42))
        assert result is expected

    def test_cache_miss_returns_none(self):
        builder = _make_builder()
        result = builder._figure_cache.get((None, 99))
        assert result is None


class TestRecordVizError:
    def test_error_recorded_in_state(self):
        builder = _make_builder()
        ctx = _make_ctx()
        builder.record_viz_error("something broke", ctx)
        assert "something broke" in ctx.state_proxy["viz_log"]["errors"]
        assert ctx.state_proxy["viz_error"] == "something broke"

    def test_error_appends_to_log(self):
        builder = _make_builder()
        ctx = _make_ctx()
        ctx.state_proxy["viz_log"] = {"errors": ["previous error"], "warnings": [], "messages": [], "frames": []}
        builder.record_viz_error("new error", ctx)
        assert "previous error" in ctx.state_proxy["viz_log"]["errors"]
        assert "new error" in ctx.state_proxy["viz_log"]["errors"]

    def test_error_handles_state_failure(self):
        """If state write fails, the method still doesn't raise."""
        builder = _make_builder()
        ctx = MagicMock()
        # Make state_proxy raise on access
        ctx.state_proxy.__getitem__ = MagicMock(side_effect=RuntimeError("state error"))
        ctx.state_proxy.__setitem__ = MagicMock(side_effect=RuntimeError("state error"))
        ctx.state_proxy.__iadd__ = MagicMock(side_effect=RuntimeError("state error"))
        builder.record_viz_error("test error", ctx)  # should not raise


class TestUpdateVizForContext:
    def test_returns_false_when_no_current_frame(self):
        builder = _make_builder()
        ctx = _make_ctx()
        ctx.vl.currentFrame = None
        ctx._vtk_scene = MagicMock()
        result = builder.update_viz_for_context(ctx, notify=False)
        assert result is False

    def test_inits_vtk_when_scene_none(self):
        builder = _make_builder()
        ctx = _make_ctx()
        ctx._vtk_scene = None
        ctx.vl.currentFrame = None
        builder.update_viz_for_context(ctx, notify=False)
        ctx.init_vtk.assert_called_once()

    def test_dispatches_to_echarts(self):
        """When objectTypes contains 'echarts', show_echarts_viz is called."""
        builder = _make_builder()
        ctx = _make_ctx()
        ctx._vtk_scene = MagicMock()
        frame = MagicMock(timestep=None, figureTitle="Test")
        ctx.vl.currentFrame = [frame]
        ctx._deckgl_view_initialized = False

        with patch("dive.builder.build.frames_to_figures",
                   return_value=(["fig_obj"], [], [], {"echarts"}, [], [])):
            with patch("backends.show_echarts_viz") as mock_echarts:
                result = builder.update_viz_for_context(ctx, notify=False)

        assert result is True
        mock_echarts.assert_called_once()
        assert ctx.state_proxy["current_viewer_type"] == "echarts"
        assert ctx.state_proxy["echarts_viewer_ready"] is True
        assert ctx.state_proxy["vtk_viewer_ready"] is False

    def test_dispatches_to_deckgl(self):
        """When objectTypes contains 'map', show_deckgl_viz is called."""
        builder = _make_builder()
        ctx = _make_ctx()
        ctx._vtk_scene = MagicMock()
        frame = MagicMock(timestep=None, figureTitle="Map", figureDescription="Desc")
        ctx.vl.currentFrame = [frame]
        ctx._deckgl_view_initialized = False

        with patch("dive.builder.build.frames_to_figures",
                   return_value=(["deck_layer"], [], [], {"map"}, [], [])):
            with patch("backends.show_deckgl_viz") as mock_deck:
                result = builder.update_viz_for_context(ctx, notify=False)

        assert result is True
        mock_deck.assert_called_once()
        assert ctx.state_proxy["current_viewer_type"] == "deckgl"

    def test_dispatches_to_vtk(self):
        """When objectTypes contains 'vtk', show_vtk_viz is called."""
        builder = _make_builder()
        ctx = _make_ctx()
        ctx._vtk_scene = MagicMock()
        frame = MagicMock(timestep=None, figureTitle="Volume")
        ctx.vl.currentFrame = [frame]
        ctx._deckgl_view_initialized = False

        with patch("dive.builder.build.frames_to_figures",
                   return_value=(["vtk_obj"], ["axes"], ["sb"], {"vtk"}, [], [])):
            with patch("backends.show_vtk_viz") as mock_vtk:
                result = builder.update_viz_for_context(ctx, notify=False)

        assert result is True
        mock_vtk.assert_called_once()
        assert ctx.state_proxy["current_viewer_type"] == "vtk"

    def test_dispatches_to_graph(self):
        """When objectTypes contains 'graph', show_graph_viz is called."""
        builder = _make_builder()
        ctx = _make_ctx()
        ctx._vtk_scene = MagicMock()
        ctx.vl.currentFrame = [MagicMock(timestep=None)]
        ctx._deckgl_view_initialized = False

        with patch("dive.builder.build.frames_to_figures",
                   return_value=(["graph_data"], [], [], {"graph"}, [], [])):
            with patch("backends.show_graph_viz") as mock_graph:
                result = builder.update_viz_for_context(ctx, notify=False)

        assert result is True
        mock_graph.assert_called_once()
        assert ctx.state_proxy["current_viewer_type"] == "graph"

    def test_dispatches_to_html(self):
        """When objectTypes contains 'html', show_html_viz is called."""
        builder = _make_builder()
        ctx = _make_ctx()
        ctx._vtk_scene = MagicMock()
        ctx.vl.currentFrame = [MagicMock(timestep=None, figureTitle="KPIs")]
        ctx._deckgl_view_initialized = False

        with patch("dive.builder.build.frames_to_figures",
                   return_value=([["cards"]], [], [], {"html"}, [], [])):
            with patch("backends.show_html_viz") as mock_html:
                result = builder.update_viz_for_context(ctx, notify=False)

        assert result is True
        mock_html.assert_called_once()
        assert ctx.state_proxy["current_viewer_type"] == "html"

    def test_unknown_type_records_error(self):
        """When objectTypes has no recognized type, records error."""
        builder = _make_builder()
        ctx = _make_ctx()
        ctx._vtk_scene = MagicMock()
        ctx.vl.currentFrame = [MagicMock(timestep=None)]
        ctx._deckgl_view_initialized = False

        with patch("dive.builder.build.frames_to_figures",
                   return_value=(["obj"], [], [], {"unknown_type"}, [], [])):
            result = builder.update_viz_for_context(ctx, notify=False)

        assert result is False
        assert ctx.state_proxy["viz_error"] is not None

    def test_cache_hit_skips_frames_to_figures(self):
        """If the cache has a matching entry, frames_to_figures is not called."""
        builder = _make_builder()
        ctx = _make_ctx()
        ctx._vtk_scene = MagicMock()
        frame = MagicMock(timestep=None)
        ctx.vl.currentFrame = [frame]
        ctx._deckgl_view_initialized = False

        # Pre-seed cache with the expected key
        cache_key = (None, builder.widget_state_hash(ctx.state_proxy))
        builder._figure_cache[cache_key] = (["fig"], [], [], {"echarts"}, [], [])

        with patch("dive.builder.build.frames_to_figures") as mock_f2f:
            with patch("backends.show_echarts_viz"):
                result = builder.update_viz_for_context(ctx, notify=False)

        assert result is True
        mock_f2f.assert_not_called()  # cache hit — no recompute


class TestBuildVizForContext:
    def test_build_sets_processing_and_clears_on_finish(self, tmp_path):
        """build_viz_for_context sets isProcessing=True then False."""
        builder = _make_builder(get_room_workspace=lambda: tmp_path)
        ctx = _make_ctx()
        ctx.workspace_path = tmp_path

        # Create a fake spec file
        spec = tmp_path / "specifications.xml"
        spec.write_text("<spec/>")

        with patch("helpers.viewer_utils") as mock_helper:
            mock_helper.file_exists.return_value = False
            builder.build_viz_for_context(ctx, str(spec))

        # After build, isProcessing should be False
        assert ctx.state_proxy["isProcessing"] is False

    def test_build_nonexistent_file_records_error(self, tmp_path):
        """Missing XML records a 'does not exist' error."""
        builder = _make_builder(get_room_workspace=lambda: tmp_path)
        ctx = _make_ctx()
        ctx.workspace_path = tmp_path

        with patch("helpers.viewer_utils") as mock_helper:
            mock_helper.file_exists.return_value = False
            builder.build_viz_for_context(ctx, str(tmp_path / "nope.xml"))

        assert ctx.state_proxy["viz_error"] is not None
        assert "does not exist" in ctx.state_proxy["viz_error"]

    def test_build_reconstructs_relative_path(self, tmp_path):
        """A bare filename is reconstructed using workspace path."""
        builder = _make_builder(get_room_workspace=lambda: tmp_path)
        ctx = _make_ctx()
        ctx.workspace_path = tmp_path

        with patch("helpers.viewer_utils") as mock_helper:
            mock_helper.file_exists.return_value = False
            builder.build_viz_for_context(ctx, "specifications.xml")

        # Should have tried the reconstructed path
        assert ctx.current_xml_path == str(tmp_path / "specifications.xml")

    def test_build_success_updates_history(self, tmp_path):
        """Successful build calls update_history_fn."""
        builder = _make_builder(get_room_workspace=lambda: tmp_path)
        ctx = _make_ctx()
        ctx.workspace_path = tmp_path
        history_calls = []

        spec = tmp_path / "DIVE" / "owner1" / "room1" / "specifications.xml"
        spec.parent.mkdir(parents=True)
        spec.write_text("<spec/>")

        with patch("helpers.viewer_utils") as mock_helper, \
             patch("dive.builder.build.build_with_history") as mock_build, \
             patch("dive.builder.build.get_timeline_info", return_value=None):
            mock_helper.file_exists.return_value = True
            mock_build.return_value = (True, "ok", False, None)
            # Mock update_viz_for_context to avoid backend dispatch
            builder.update_viz_for_context = MagicMock(return_value=True)

            builder.build_viz_for_context(
                ctx, str(spec),
                update_history_fn=lambda c: history_calls.append(c),
            )

        assert len(history_calls) == 1
        assert history_calls[0] is ctx
