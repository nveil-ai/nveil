# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for DashboardManager — sequential panel building."""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch


from managers.dashboard_manager import DashboardManager


def _make_ctx(panel_id, workspace_path=None, has_cg=False, has_spec=False):
    """Create a minimal fake VizContext for dashboard tests."""
    ctx = MagicMock()
    ctx.panel_id = panel_id
    ctx.workspace_path = Path(workspace_path) if workspace_path else None
    ctx.choregraph = None
    ctx.vl = MagicMock()
    ctx.vl.choregraph = None
    return ctx


class TestBuildAllPanels:
    @pytest.mark.asyncio
    async def test_skips_main_context(self):
        """Main context is never built as a panel."""
        build_calls = []
        mgr = DashboardManager(
            get_contexts=lambda: {"main": MagicMock()},
            build_viz_fn=lambda ctx, path: build_calls.append((ctx, path)),
            record_error_fn=lambda msg, ctx: None,
        )
        await mgr.build_all_panels()
        assert len(build_calls) == 0

    @pytest.mark.asyncio
    async def test_records_error_for_missing_workspace(self, tmp_path):
        """Panel with nonexistent workspace records an error."""
        errors = []
        ctx = _make_ctx("panel_1", workspace_path=str(tmp_path / "nonexistent"))
        mgr = DashboardManager(
            get_contexts=lambda: {"main": MagicMock(), "panel_1": ctx},
            build_viz_fn=lambda ctx, path: None,
            record_error_fn=lambda msg, ctx: errors.append(msg),
        )
        await mgr.build_all_panels()
        assert len(errors) == 1
        assert "missing" in errors[0].lower() or "re-upload" in errors[0].lower()

    @pytest.mark.asyncio
    async def test_builds_panel_with_spec(self, tmp_path):
        """Panel with specifications.xml triggers build_viz."""
        ws = tmp_path / "panel_ws"
        ws.mkdir()
        (ws / "specifications.xml").write_text("<spec/>")

        build_calls = []
        ctx = _make_ctx("panel_1", workspace_path=str(ws))
        ctx.workspace_path = ws  # Path object

        mgr = DashboardManager(
            get_contexts=lambda: {"main": MagicMock(), "panel_1": ctx},
            build_viz_fn=lambda c, path: build_calls.append(path),
            record_error_fn=lambda msg, ctx: None,
        )
        await mgr.build_all_panels()
        assert len(build_calls) == 1
        assert "specifications.xml" in build_calls[0]

    @pytest.mark.asyncio
    async def test_records_error_for_missing_spec(self, tmp_path):
        """Panel with workspace but no spec records an error."""
        ws = tmp_path / "panel_ws2"
        ws.mkdir()
        # No specifications.xml

        errors = []
        ctx = _make_ctx("panel_1", workspace_path=str(ws))
        ctx.workspace_path = ws

        mgr = DashboardManager(
            get_contexts=lambda: {"main": MagicMock(), "panel_1": ctx},
            build_viz_fn=lambda c, path: None,
            record_error_fn=lambda msg, ctx: errors.append(msg),
        )
        await mgr.build_all_panels()
        assert any("specification missing" in e.lower() for e in errors)

    @pytest.mark.asyncio
    async def test_choregraph_pipeline_failure_records_error(self, tmp_path):
        """Pipeline failure records an error but continues to try spec build."""
        ws = tmp_path / "panel_ws3"
        ws.mkdir()
        (ws / "choregraph.xml").write_text("<cg/>")
        (ws / "specifications.xml").write_text("<spec/>")

        errors = []
        build_calls = []
        ctx = _make_ctx("panel_1", workspace_path=str(ws))
        ctx.workspace_path = ws

        fake_cg = MagicMock()
        fake_cg.run.return_value = (False, "pipeline error")

        with patch("choregraph.Choregraph", return_value=fake_cg):
            mgr = DashboardManager(
                get_contexts=lambda: {"main": MagicMock(), "panel_1": ctx},
                build_viz_fn=lambda c, path: build_calls.append(path),
                record_error_fn=lambda msg, ctx: errors.append(msg),
            )
            await mgr.build_all_panels()

        assert any("processing failed" in e.lower() for e in errors)
        # Spec build still attempted
        assert len(build_calls) == 1

    @pytest.mark.asyncio
    async def test_multiple_panels_built_sequentially(self, tmp_path):
        """Multiple panels are built in order."""
        order = []
        contexts = {"main": MagicMock()}

        for i in range(3):
            ws = tmp_path / f"panel_{i}"
            ws.mkdir()
            (ws / "specifications.xml").write_text("<spec/>")
            ctx = _make_ctx(f"panel_{i}", workspace_path=str(ws))
            ctx.workspace_path = ws
            contexts[f"panel_{i}"] = ctx

        mgr = DashboardManager(
            get_contexts=lambda: contexts,
            build_viz_fn=lambda c, path: order.append(c.panel_id),
            record_error_fn=lambda msg, ctx: None,
        )
        await mgr.build_all_panels()
        assert len(order) == 3
