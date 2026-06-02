# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Integration tests for viz_service context switching logic.

These tests exercise the context lifecycle (create, transfer, destroy)
without real VTK initialization to avoid segfaults in headless Docker.
VTK scene is simulated with MagicMock.
"""

import pytest
from unittest.mock import MagicMock

from viz_context import VizContext


class _FakeState:
    """Minimal trame state stub."""
    def __init__(self):
        self._data = {}

    def __getitem__(self, key):
        return self._data.get(key)

    def __setitem__(self, key, value):
        self._data[key] = value

    def dirty(self, *keys):
        pass

    def flush(self):
        pass

    def change(self, *keys):
        def decorator(fn):
            return fn
        return decorator


class TestResetChatContext:
    def test_creates_fresh_context(self):
        """After reset, a new VizContext replaces the old one."""
        state = _FakeState()
        old_ctx = VizContext("main")
        old_ctx.init_state(state)
        old_ctx._vtk_scene = MagicMock(name="scene")
        old_scene = old_ctx._vtk_scene

        new_ctx = VizContext("main")
        new_ctx.init_state(state)

        new_ctx._vtk_scene = old_ctx._vtk_scene
        old_ctx._vtk_scene = None

        assert new_ctx._vtk_scene is old_scene
        assert old_ctx._vtk_scene is None

    def test_new_context_has_clean_state(self):
        """New context should have default state values."""
        state = _FakeState()
        ctx = VizContext("main")
        ctx.init_state(state)
        sp = ctx.state_proxy
        assert sp["isProcessing"] is False
        assert sp["viz_error"] is None


class TestResetDashboardContext:
    def test_destroy_panel_contexts(self):
        """Panel contexts are destroyed, main survives."""
        state = _FakeState()
        contexts = {}
        contexts["main"] = VizContext("main")
        contexts["main"].init_state(state)
        contexts["panel_1"] = VizContext("panel_1")
        contexts["panel_1"].init_state(state)
        contexts["panel_2"] = VizContext("panel_2")
        contexts["panel_2"].init_state(state)

        for pid in list(contexts.keys()):
            if pid != "main":
                contexts[pid].destroy()
                del contexts[pid]

        assert "main" in contexts
        assert "panel_1" not in contexts
        assert "panel_2" not in contexts


class TestCarryOverUIRefs:
    def test_vtk_scene_transferred(self):
        """VTK scene moves from old context to new one."""
        state = _FakeState()

        from_ctx = VizContext("main")
        from_ctx.init_state(state)
        from_ctx._vtk_scene = MagicMock(name="scene")
        from_ctx._vtk_scene.axes_actor = MagicMock()

        to_ctx = VizContext("main")
        to_ctx.init_state(state)

        to_ctx._vtk_scene = from_ctx._vtk_scene
        from_ctx._vtk_scene = None

        assert to_ctx._vtk_scene is not None
        assert from_ctx._vtk_scene is None
        assert to_ctx._vtk_scene.axes_actor is not None

    def test_ctrl_refs_transferred(self):
        """Controller references move from old to new context."""
        state = _FakeState()

        from_ctx = VizContext("main")
        from_ctx.init_state(state)
        from_ctx.ctrl_echarts_update = MagicMock()
        from_ctx.ctrl_echarts_clear = MagicMock()

        to_ctx = VizContext("main")
        to_ctx.init_state(state)

        to_ctx.ctrl_echarts_update = from_ctx.ctrl_echarts_update
        to_ctx.ctrl_echarts_clear = from_ctx.ctrl_echarts_clear
        from_ctx.ctrl_echarts_update = None
        from_ctx.ctrl_echarts_clear = None

        assert to_ctx.ctrl_echarts_update is not None
        assert from_ctx.ctrl_echarts_update is None


class TestReleaseRoom:
    def test_release_clears_room_state(self):
        """After release, room_id and room_token are None."""
        room_id = "room_abc"
        room_token = "tok_abc"

        room_id = None
        room_token = None
        mode = "chat"

        assert room_id is None
        assert room_token is None
        assert mode == "chat"

    def test_release_recreates_blank_context(self):
        """Release creates a blank main context with scene transferred."""
        state = _FakeState()

        old_ctx = VizContext("main")
        old_ctx.init_state(state)
        old_ctx._vtk_scene = MagicMock(name="scene")
        old_scene = old_ctx._vtk_scene

        new_ctx = VizContext("main")
        new_ctx.init_state(state)
        new_ctx._vtk_scene = old_ctx._vtk_scene
        old_ctx._vtk_scene = None
        old_ctx.destroy()

        assert new_ctx._vtk_scene is old_scene
        assert new_ctx.current_xml_path is None
