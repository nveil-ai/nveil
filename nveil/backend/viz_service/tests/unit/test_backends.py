# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for visualization backends — ECharts, VTK, DeckGL, Graph, HTML."""

import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# ECharts
# ---------------------------------------------------------------------------


class TestEchartsBackend:
    def _ctx(self, panel_id="main"):
        ctx = MagicMock()
        ctx.ctrl_echarts_update = MagicMock()
        ctx.panel_id = panel_id
        ctx.state_proxy = MagicMock()
        ctx.state_proxy.PlotTheme = "deep_blue"
        return ctx

    def test_single_option_calls_ctrl(self):
        from backends.echarts_backend import show_echarts_viz

        ctx = self._ctx()
        option = {"series": [{"type": "bar", "data": [1, 2, 3]}]}
        show_echarts_viz(ctx, [option])
        ctx.ctrl_echarts_update.assert_called_once()
        sent = ctx.ctrl_echarts_update.call_args.args[0]
        assert sent["series"][0]["type"] == "bar"
        assert "grid" in sent

    def test_multiple_options_merged(self):
        from backends.echarts_backend import show_echarts_viz

        ctx = self._ctx()
        o1 = {"series": [{"type": "bar", "data": [1]}]}
        o2 = {"series": [{"type": "bar", "data": [2]}]}
        show_echarts_viz(ctx, [o1, o2])
        sent = ctx.ctrl_echarts_update.call_args.args[0]
        assert len(sent["series"]) == 2

    def test_dashboard_panel_applies_grid(self):
        from backends.echarts_backend import show_echarts_viz

        ctx = self._ctx(panel_id="panel_1")
        show_echarts_viz(ctx, [{"series": [{"type": "bar", "data": [1]}]}])
        sent = ctx.ctrl_echarts_update.call_args.args[0]
        assert "grid" in sent

    def test_empty_options_noop(self):
        from backends.echarts_backend import show_echarts_viz

        ctx = self._ctx()
        show_echarts_viz(ctx, [])
        ctx.ctrl_echarts_update.assert_not_called()

    def test_missing_ctrl_raises(self):
        from backends.echarts_backend import show_echarts_viz

        ctx = MagicMock()
        ctx.ctrl_echarts_update = None
        ctx.panel_id = "main"
        ctx.state_proxy = MagicMock()
        ctx.state_proxy.PlotTheme = "deep_blue"
        with pytest.raises(RuntimeError):
            show_echarts_viz(ctx, [{"series": [{"type": "bar"}]}])

    def test_polar_to_cartesian_bar_triggers_clear(self):
        # Polar bar and cartesian bar share series ``type: "bar"``; only the
        # ``coordinateSystem`` key on the series differs. Without including it
        # in the signature, the polar→cartesian transition would skip
        # ``ctrl_echarts_clear`` and leave stale ``polar``/``angleAxis``/
        # ``radiusAxis`` components alive under echarts' merge semantics.
        from backends.echarts_backend import show_echarts_viz

        ctx = self._ctx()
        ctx.ctrl_echarts_clear = MagicMock()

        polar_bar = {
            "series": [{"type": "bar", "coordinateSystem": "polar"}],
            "polar": {},
            "angleAxis": {"type": "category"},
            "radiusAxis": {},
        }
        show_echarts_viz(ctx, [polar_bar])
        ctx.ctrl_echarts_clear.reset_mock()

        cartesian_bar = {"series": [{"type": "bar"}]}
        show_echarts_viz(ctx, [cartesian_bar])
        ctx.ctrl_echarts_clear.assert_called_once()


# ---------------------------------------------------------------------------
# VTK
# ---------------------------------------------------------------------------


class TestVTKBackend:
    def test_ensure_vtk_initialized_idempotent(self):
        vtk = pytest.importorskip("vtk", reason="vtk not installed")
        from dive.builder.vtk import VtkScene
        from backends.vtk_backend import ensure_vtk_initialized

        scene = VtkScene.create(offscreen=True)
        scene.setup_orientation_widget()
        ctx = MagicMock()
        ctx._vtk_scene = scene
        ensure_vtk_initialized(ctx)
        assert scene.axes_actor is not None

    def test_ensure_vtk_initialized_creates_widget(self):
        vtk = pytest.importorskip("vtk", reason="vtk not installed")
        from dive.builder.vtk import VtkScene
        from backends.vtk_backend import ensure_vtk_initialized

        scene = VtkScene.create(offscreen=True)
        assert scene.axes_actor is None
        ctx = MagicMock()
        ctx._vtk_scene = scene
        ensure_vtk_initialized(ctx)
        assert scene.axes_actor is not None

    def test_show_vtk_viz_adds_actors(self):
        vtk = pytest.importorskip("vtk", reason="vtk not installed")
        from dive.builder.vtk import VtkScene
        from backends.vtk_backend import show_vtk_viz

        scene = VtkScene.create(offscreen=True)
        scene.setup_orientation_widget()
        ctx = MagicMock()
        ctx._vtk_scene = scene
        ctx.ctrl_view_update = MagicMock()
        ctx.state_proxy = MagicMock()
        ctx.state_proxy.get = MagicMock(return_value=False)

        mapper = vtk.vtkPolyDataMapper()
        viz_obj = [{"volume": False, "mapper": mapper}]
        show_vtk_viz(ctx, viz_obj, [], [])
        ctx.ctrl_view_update.assert_called_once()


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


class TestGraphBackend:
    def test_pushes_graph_data_to_state(self):
        from backends.graph_backend import show_graph_viz

        ctx = MagicMock()
        sp = MagicMock()
        sp.trigger_update_data = 0
        ctx.state_proxy = sp

        graph_obj = {"graph_object": {"nodes": [], "links": []}, "is_3d": False}
        show_graph_viz(ctx, [graph_obj])
        assert sp.graph_data == {"nodes": [], "links": []}
        assert sp.is_3d is False


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------


class _DirtyDict(dict):
    """Dict that tracks dirty calls like trame state. Always truthy."""
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.dirty_calls = []

    def __bool__(self):
        return True  # trame state proxy is always truthy

    def dirty(self, *keys):
        self.dirty_calls.extend(keys)


class TestHTMLBackend:
    def test_empty_cards_clears_state(self):
        from backends.html_backend import show_html_viz

        ctx = MagicMock()
        sp = _DirtyDict()
        ctx.state_proxy = sp

        show_html_viz(ctx, [])
        assert sp["html_card_groups"] == []
        assert sp["html_figure_title"] == ""

    def test_cards_pushed_to_state(self):
        from backends.html_backend import show_html_viz

        ctx = MagicMock()
        sp = _DirtyDict()
        ctx.state_proxy = sp

        groups = [
            {"group_label": "KPIs", "z_title": "val", "cards": [{"label": "A", "value": 42}]}
        ]
        show_html_viz(ctx, groups, figure_title="My KPIs")
        assert sp["html_figure_title"] == "My KPIs"
        assert sp["html_card_groups"] == groups
        assert "html_card_groups" in sp.dirty_calls


# ---------------------------------------------------------------------------
# DeckGL
# ---------------------------------------------------------------------------


class TestDeckGLBackend:
    def test_empty_layers_clears_legend(self):
        from backends.deckgl_backend import show_deckgl_viz

        ctx = MagicMock()
        sp = _DirtyDict()
        ctx.state_proxy = sp
        ctx._deckgl_view_initialized = False

        show_deckgl_viz(ctx, [])
        assert sp["deckgl_legend_html"] == ""

    def test_none_layers_filtered(self):
        from backends.deckgl_backend import show_deckgl_viz

        ctx = MagicMock()
        sp = _DirtyDict()
        ctx.state_proxy = sp
        ctx._deckgl_view_initialized = False

        show_deckgl_viz(ctx, [None, None])
        assert sp["deckgl_legend_html"] == ""

    def test_valid_layer_sets_view(self):
        pdk = pytest.importorskip("pydeck", reason="pydeck not installed")
        import pandas as pd
        from backends.deckgl_backend import show_deckgl_viz

        layer = MagicMock()
        layer.data = pd.DataFrame({"position": [[0, 0], [1, 1]]})
        layer.description = None

        ctx = MagicMock()
        sp = _DirtyDict()
        ctx.state_proxy = sp
        ctx._deckgl_view_initialized = False
        ctx.ctrl_deck_update = MagicMock()

        show_deckgl_viz(ctx, [layer])
        ctx.ctrl_deck_update.assert_called_once()
        assert ctx._deckgl_view_initialized is True
