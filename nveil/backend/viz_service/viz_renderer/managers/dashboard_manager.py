# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Dashboard mode — sequential panel build and lifecycle."""

import asyncio
from logging import ERROR, WARNING
from typing import Callable, Dict

from logger import INFO, logger


class DashboardManager:
    """Manages building dashboard panels sequentially.

    The layout/Trame glue (init_dashboard_mode) stays in App because it's
    tightly coupled to create_panel_template and build_dashboard_layout.
    This class owns the build-all-panels logic which is independently testable.

    Args:
        get_contexts: Callable returning the contexts dict.
        build_viz_fn: Callback ``(ctx, xml_path) -> None`` to build a single panel.
        record_error_fn: Callback ``(msg, ctx) -> None`` to record errors.
    """

    def __init__(
        self,
        get_contexts: Callable,
        build_viz_fn: Callable,
        record_error_fn: Callable,
    ):
        self._get_contexts = get_contexts
        self._build_viz = build_viz_fn
        self._record_error = record_error_fn

    async def build_all_panels(self):
        """Initialize Choregraph and build viz for each dashboard panel.

        Panels are built sequentially because Kedro's bootstrap_project,
        os.chdir (pushd), and sys.modules/sys.path mutations are
        process-global — running multiple pipelines in parallel threads
        causes race conditions.
        """
        from choregraph import Choregraph as CG

        contexts = self._get_contexts()

        for panel_id, ctx in contexts.items():
            if panel_id == "main":
                continue

            if not ctx.workspace_path or not ctx.workspace_path.exists():
                logger().logp(WARNING, f"Panel {panel_id}: workspace not found, skipping")
                self._record_error("Data sources missing — please re-upload or re-link the data.", ctx)
                continue

            try:
                cg_xml = ctx.workspace_path / "choregraph.xml"
                spec_xml = ctx.workspace_path / "specifications.xml"

                if cg_xml.exists():
                    # Run heavy sync operations in a thread so the event loop
                    # stays free to serve iframe requests and push spinner state.
                    ctx.choregraph = await asyncio.to_thread(
                        CG, str(cg_xml), workspace_path=ctx.workspace_path
                    )
                    ctx.vl.choregraph = ctx.choregraph

                    run_success, run_error = await asyncio.to_thread(
                        ctx.choregraph.run, lazy=True
                    )
                    if not run_success:
                        logger().logp(WARNING, f"Panel {panel_id}: pipeline failed: {run_error}")
                        self._record_error("Data processing failed — source data may have been removed.", ctx)

                if spec_xml.exists():
                    # _build_viz touches Trame state — must stay on event loop thread
                    self._build_viz(ctx, str(spec_xml))
                    logger().logp(INFO, f"Panel {panel_id}: viz built successfully")
                else:
                    logger().logp(WARNING, f"Panel {panel_id}: no specifications.xml found")
                    self._record_error("Visualization specification missing.", ctx)

            except Exception as e:
                logger().logp(ERROR, f"Panel {panel_id}: init failed: {e}")
                self._record_error(f"Panel initialization failed: {e}", ctx)

            await asyncio.sleep(0)
