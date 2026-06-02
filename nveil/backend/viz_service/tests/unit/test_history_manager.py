# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for HistoryManager — file scanning and navigation."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from managers.history_manager import HistoryManager


class _FakeCtx:
    """Minimal VizContext stand-in for history tests."""
    def __init__(self, current_xml_path=None):
        self.current_xml_path = current_xml_path
        self.history_files = []
        self.current_history_index = -1
        self.state_proxy = {}

    class state_proxy(dict):
        """Dict that also supports attribute-style __setitem__."""
        pass

    def __init__(self, current_xml_path=None):
        self.current_xml_path = current_xml_path
        self.history_files = []
        self.current_history_index = -1
        self.state_proxy = _FakeCtx.state_proxy()


@pytest.fixture
def build_calls():
    """Track calls to the build_viz callback."""
    calls = []
    def build_viz(ctx, path):
        calls.append((ctx, path))
    return calls, build_viz


class TestUpdateHistoryList:
    def test_no_current_path(self, build_calls):
        calls, build_fn = build_calls
        mgr = HistoryManager(build_fn)
        ctx = _FakeCtx(current_xml_path=None)
        mgr.update_history_list(ctx)
        assert ctx.history_files == []
        assert ctx.current_history_index == -1

    def test_scans_files(self, tmp_path, build_calls):
        calls, build_fn = build_calls
        # Create fake spec files
        for i in range(3):
            (tmp_path / f"specificationsEnhanced_{i:03d}.xml").write_text("<xml/>")
        current = str(tmp_path / "specificationsEnhanced_001.xml")

        mgr = HistoryManager(build_fn)
        ctx = _FakeCtx(current_xml_path=current)
        mgr.update_history_list(ctx)

        assert len(ctx.history_files) == 3
        assert ctx.current_history_index == 1  # points to _001

    def test_current_not_in_list_defaults_to_last(self, tmp_path, build_calls):
        calls, build_fn = build_calls
        (tmp_path / "specificationsEnhanced_000.xml").write_text("<xml/>")
        current = str(tmp_path / "specifications.xml")  # not in glob result

        mgr = HistoryManager(build_fn)
        ctx = _FakeCtx(current_xml_path=current)
        mgr.update_history_list(ctx)

        assert ctx.current_history_index == 0  # last (only) file


class TestNavigation:
    def test_previous(self, build_calls):
        calls, build_fn = build_calls
        mgr = HistoryManager(build_fn)
        ctx = _FakeCtx()
        ctx.history_files = ["/a.xml", "/b.xml", "/c.xml"]
        ctx.current_history_index = 2

        mgr.previous_viz(ctx)
        assert len(calls) == 1
        assert calls[0][1] == "/b.xml"

    def test_previous_at_zero_noop(self, build_calls):
        calls, build_fn = build_calls
        mgr = HistoryManager(build_fn)
        ctx = _FakeCtx()
        ctx.history_files = ["/a.xml"]
        ctx.current_history_index = 0

        mgr.previous_viz(ctx)
        assert len(calls) == 0

    def test_next(self, build_calls):
        calls, build_fn = build_calls
        mgr = HistoryManager(build_fn)
        ctx = _FakeCtx()
        ctx.history_files = ["/a.xml", "/b.xml", "/c.xml"]
        ctx.current_history_index = 0

        mgr.next_viz(ctx)
        assert len(calls) == 1
        assert calls[0][1] == "/b.xml"

    def test_next_at_end_noop(self, build_calls):
        calls, build_fn = build_calls
        mgr = HistoryManager(build_fn)
        ctx = _FakeCtx()
        ctx.history_files = ["/a.xml"]
        ctx.current_history_index = 0

        mgr.next_viz(ctx)
        assert len(calls) == 0

    def test_load_out_of_bounds_noop(self, build_calls):
        calls, build_fn = build_calls
        mgr = HistoryManager(build_fn)
        ctx = _FakeCtx()
        ctx.history_files = ["/a.xml"]

        mgr.load_history_viz(5, ctx)
        assert len(calls) == 0
