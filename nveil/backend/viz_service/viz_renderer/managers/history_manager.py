# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""History navigation — scan workspace for versioned spec files and navigate."""

from pathlib import Path
from typing import Callable, Optional

from logger import logger


class HistoryManager:
    """Manages navigation through versioned specification XML files.

    Args:
        build_viz_fn: Callback to build visualization from a spec file path.
                      Signature: (ctx, xml_path: str) -> None
    """

    def __init__(self, build_viz_fn: Callable):
        self._build_viz = build_viz_fn

    def update_history_list(self, ctx) -> None:
        """Scan workspace for specificationsEnhanced_*.xml and update context."""
        sp = ctx.state_proxy

        if not ctx.current_xml_path:
            sp["history_files"] = []
            sp["current_history_index"] = -1
            ctx.history_files = []
            ctx.current_history_index = -1
            return

        p = Path(ctx.current_xml_path).parent
        files = sorted(p.glob("specificationsEnhanced_*.xml"), key=lambda x: x.name)

        ctx.history_files = [str(f) for f in files]
        sp["history_files"] = ctx.history_files

        try:
            ctx.current_history_index = ctx.history_files.index(str(ctx.current_xml_path))
        except ValueError:
            ctx.current_history_index = len(ctx.history_files) - 1 if ctx.history_files else -1

        sp["current_history_index"] = ctx.current_history_index

    def load_history_viz(self, index: int, ctx) -> None:
        """Load a visualization from history by index."""
        if 0 <= index < len(ctx.history_files):
            file_path = ctx.history_files[index]
            self._build_viz(ctx, file_path)

    def previous_viz(self, ctx) -> None:
        """Navigate to the previous visualization in history."""
        if ctx.current_history_index > 0:
            self.load_history_viz(ctx.current_history_index - 1, ctx)

    def next_viz(self, ctx) -> None:
        """Navigate to the next visualization in history."""
        if ctx.current_history_index < len(ctx.history_files) - 1:
            self.load_history_viz(ctx.current_history_index + 1, ctx)
