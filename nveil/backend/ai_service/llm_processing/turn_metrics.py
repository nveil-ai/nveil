# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Per-turn metrics accumulator for LLM calls.

Creates a session-scoped ``TurnMetrics`` object via ``contextvars`` so that
every ``LLMManager.ainvoke`` / ``invoke`` call within a single
``chat_endpoint`` turn automatically records its timing and token usage.

Usage in ``ai_server.py``::

    from llm_processing.turn_metrics import TurnMetrics, set_turn_metrics

    tm = TurnMetrics()
    set_turn_metrics(tm)
    tm.set_context(room_id=..., owner_id=..., user_id=...)
    # … invoke graphs …
    logger().logp(INFO, tm.format_table())
    await tm.persist_to_db()
"""

from __future__ import annotations

import contextvars
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StepRecord:
    label: str
    elapsed_s: float
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0


# Maps cost_label strings to (column_prefix, supports_attempts).
# Labels mapping to the same prefix are grouped and assigned attempt numbers.
_LABEL_MAP: dict[str, tuple[str, bool]] = {
    "Entry Point Message Type Classification": ("entry_classif", False),
    "Transformation XML Generation":           ("planning", True),
    "XML Generation Node with Cache":          ("xml_gen", True),
    "XML Generation Node without Cache":       ("xml_gen", True),
    "Keyword Classification":                  ("keyword_classif", False),
    "Exclusion Processing Node":               ("exclusion", False),
}

_ATTEMPT_SUFFIXES = ["1st", "2nd", "3rd"]
_METRIC_FIELDS = ["elapsed_s", "input_tokens", "cached_tokens", "output_tokens", "thinking_tokens"]


class TurnMetrics:
    """Accumulates :class:`StepRecord` entries across LLM calls."""

    def __init__(self) -> None:
        self.steps: list[StepRecord] = []
        self.node_retries: dict[str, int] = {}
        self._room_id: str | None = None
        self._owner_id: str | None = None
        self._user_id: str | None = None
        self._source: str = "web"

    def set_context(
        self,
        *,
        room_id: str,
        owner_id: str,
        user_id: str,
        source: str = "web",
    ) -> None:
        """Attach request context so ``persist_to_db`` can store it."""
        self._room_id = room_id
        self._owner_id = owner_id
        self._user_id = user_id
        self._source = source

    def record(self, label: str, elapsed_s: float, usage: dict) -> None:
        """Append a step from the usage dict produced by ``_extract_usage_from_callback``.

        The *usage* dict is the **inner** dict (not keyed by model name) with
        keys like ``input_tokens``, ``output_tokens``,
        ``input_token_details.cache_read``, ``output_token_details.reasoning``.
        """
        input_tokens = usage.get("input_tokens", 0) or 0
        cached_tokens = (
            (usage.get("input_token_details") or {}).get("cache_read", 0) or 0
        )
        output_tokens = usage.get("output_tokens", 0) or 0
        thinking_tokens = (
            (usage.get("output_token_details") or {}).get("reasoning", 0) or 0
        )
        self.steps.append(
            StepRecord(
                label=label,
                elapsed_s=elapsed_s,
                input_tokens=input_tokens,
                cached_tokens=cached_tokens,
                output_tokens=output_tokens,
                thinking_tokens=thinking_tokens,
            )
        )

    def record_retries(self, node_label: str, retries: int) -> None:
        """Record how many retries a node required (0 = success on first attempt)."""
        self.node_retries[node_label] = retries

    # ------------------------------------------------------------------
    # Pretty-print
    # ------------------------------------------------------------------

    def format_table(self) -> str:
        """Return an ASCII box-drawing table summarising all recorded steps."""
        if not self.steps:
            return "📊 Turn metrics: no LLM calls recorded."

        headers = ("Step", "Time", "Input", "Cache", "Output", "Thinking")

        def _fmt_int(n: int) -> str:
            return f"{n:,}" if n else "—"

        rows: list[tuple[str, ...]] = []
        for s in self.steps:
            rows.append((
                s.label,
                f"{s.elapsed_s:.2f}s",
                _fmt_int(s.input_tokens),
                _fmt_int(s.cached_tokens),
                _fmt_int(s.output_tokens),
                _fmt_int(s.thinking_tokens),
            ))

        # Totals
        tot_time = sum(s.elapsed_s for s in self.steps)
        tot_input = sum(s.input_tokens for s in self.steps)
        tot_cache = sum(s.cached_tokens for s in self.steps)
        tot_output = sum(s.output_tokens for s in self.steps)
        tot_think = sum(s.thinking_tokens for s in self.steps)
        totals = (
            "Total",
            f"~{tot_time:.1f}s",
            _fmt_int(tot_input),
            _fmt_int(tot_cache),
            _fmt_int(tot_output),
            _fmt_int(tot_think),
        )

        # Column widths (max of header, every row, and totals)
        widths = [len(h) for h in headers]
        for row in [*rows, totals]:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(cell))

        def _line(left: str, mid: str, right: str, fill: str = "─") -> str:
            return left + mid.join(fill * (w + 2) for w in widths) + right

        def _row(cells: tuple[str, ...], align_right_from: int = 1) -> str:
            parts: list[str] = []
            for i, (cell, w) in enumerate(zip(cells, widths)):
                if i >= align_right_from:
                    parts.append(f" {cell:>{w}} ")
                else:
                    parts.append(f" {cell:<{w}} ")
            return "│" + "│".join(parts) + "│"

        lines: list[str] = [
            "",
            "📊 Turn LLM metrics:",
            _line("┌", "┬", "┐"),
            _row(headers, align_right_from=1),
            _line("├", "┼", "┤"),
        ]
        for r in rows:
            lines.append(_row(r))
        lines.append(_line("├", "┼", "┤"))
        lines.append(_row(totals))
        lines.append(_line("└", "┴", "┘"))

        # Node retry summary
        if self.node_retries:
            parts = [f"{node}: {count}" for node, count in self.node_retries.items()]
            lines.append(f"🔄 Node retries: {', '.join(parts)}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Database persistence
    # ------------------------------------------------------------------

    async def persist_to_db(self) -> None:
        """Insert a row into ``turn_metrics`` with per-step and per-attempt data.

        Non-blocking: logs a warning on failure instead of raising.
        """
        from database.database import db
        from database.model import TurnMetricsRecord

        try:
            row_data: dict = {
                "room_id": self._room_id,
                "owner_id": self._owner_id,
                "user_id": self._user_id,
                "source": self._source,
            }

            # Group steps by column prefix and preserve insertion order
            prefix_steps: dict[str, list[StepRecord]] = defaultdict(list)
            for step in self.steps:
                mapping = _LABEL_MAP.get(step.label)
                if mapping is None:
                    continue  # skip unmapped steps (e.g. feedback)
                prefix, _ = mapping
                prefix_steps[prefix].append(step)

            # Fill per-step / per-attempt columns
            for prefix, steps_list in prefix_steps.items():
                mapping = next(
                    (v for v in _LABEL_MAP.values() if v[0] == prefix), None
                )
                if mapping is None:
                    continue
                _, supports_attempts = mapping

                if supports_attempts:
                    for idx, step in enumerate(steps_list):
                        if idx >= len(_ATTEMPT_SUFFIXES):
                            break
                        suffix = _ATTEMPT_SUFFIXES[idx]
                        col_prefix = f"{prefix}_{suffix}"
                        row_data[f"{col_prefix}_elapsed_s"] = step.elapsed_s
                        row_data[f"{col_prefix}_input_tokens"] = step.input_tokens
                        row_data[f"{col_prefix}_cached_tokens"] = step.cached_tokens
                        row_data[f"{col_prefix}_output_tokens"] = step.output_tokens
                        row_data[f"{col_prefix}_thinking_tokens"] = step.thinking_tokens
                else:
                    step = steps_list[0]
                    row_data[f"{prefix}_elapsed_s"] = step.elapsed_s
                    row_data[f"{prefix}_input_tokens"] = step.input_tokens
                    row_data[f"{prefix}_cached_tokens"] = step.cached_tokens
                    row_data[f"{prefix}_output_tokens"] = step.output_tokens
                    row_data[f"{prefix}_thinking_tokens"] = step.thinking_tokens

            # Retry counts
            row_data["planning_retries"] = self.node_retries.get("Planning Transformation", 0)
            row_data["xml_gen_retries"] = self.node_retries.get("XML Generation", 0)

            # Totals
            row_data["total_elapsed_s"] = sum(s.elapsed_s for s in self.steps)
            row_data["total_input_tokens"] = sum(s.input_tokens for s in self.steps)
            row_data["total_cached_tokens"] = sum(s.cached_tokens for s in self.steps)
            row_data["total_output_tokens"] = sum(s.output_tokens for s in self.steps)
            row_data["total_thinking_tokens"] = sum(s.thinking_tokens for s in self.steps)

            async with db.session() as session:
                session.add(TurnMetricsRecord(**row_data))

        except Exception as exc:
            try:
                from logger import WARNING, logger as get_logger
                get_logger().logp(WARNING, f"⚠️ Failed to persist turn metrics: {exc}")
            except Exception:
                pass

    async def update_in_db(self) -> None:
        """Update an existing row (matched by room_id) with new step data.

        Used by the second SDK call to add viz metrics to the row
        inserted by the first call.
        """
        from database.database import db
        from database.model import TurnMetricsRecord
        from sqlalchemy import update as sa_update

        if not self._room_id:
            return

        try:
            row_data: dict = {}

            prefix_steps: dict[str, list[StepRecord]] = defaultdict(list)
            for step in self.steps:
                mapping = _LABEL_MAP.get(step.label)
                if mapping is None:
                    continue
                prefix, _ = mapping
                prefix_steps[prefix].append(step)

            for prefix, steps_list in prefix_steps.items():
                mapping = next(
                    (v for v in _LABEL_MAP.values() if v[0] == prefix), None
                )
                if mapping is None:
                    continue
                _, supports_attempts = mapping

                if supports_attempts:
                    for idx, step in enumerate(steps_list):
                        if idx >= len(_ATTEMPT_SUFFIXES):
                            break
                        suffix = _ATTEMPT_SUFFIXES[idx]
                        col_prefix = f"{prefix}_{suffix}"
                        row_data[f"{col_prefix}_elapsed_s"] = step.elapsed_s
                        row_data[f"{col_prefix}_input_tokens"] = step.input_tokens
                        row_data[f"{col_prefix}_cached_tokens"] = step.cached_tokens
                        row_data[f"{col_prefix}_output_tokens"] = step.output_tokens
                        row_data[f"{col_prefix}_thinking_tokens"] = step.thinking_tokens
                else:
                    step = steps_list[0]
                    row_data[f"{prefix}_elapsed_s"] = step.elapsed_s
                    row_data[f"{prefix}_input_tokens"] = step.input_tokens
                    row_data[f"{prefix}_cached_tokens"] = step.cached_tokens
                    row_data[f"{prefix}_output_tokens"] = step.output_tokens
                    row_data[f"{prefix}_thinking_tokens"] = step.thinking_tokens

            row_data["xml_gen_retries"] = self.node_retries.get("XML Generation", 0)

            # Recompute totals from both steps (read existing + add new)
            all_steps = self.steps
            row_data["total_elapsed_s"] = TurnMetricsRecord.total_elapsed_s + sum(s.elapsed_s for s in all_steps)
            row_data["total_input_tokens"] = TurnMetricsRecord.total_input_tokens + sum(s.input_tokens for s in all_steps)
            row_data["total_cached_tokens"] = TurnMetricsRecord.total_cached_tokens + sum(s.cached_tokens for s in all_steps)
            row_data["total_output_tokens"] = TurnMetricsRecord.total_output_tokens + sum(s.output_tokens for s in all_steps)
            row_data["total_thinking_tokens"] = TurnMetricsRecord.total_thinking_tokens + sum(s.thinking_tokens for s in all_steps)

            async with db.session() as session:
                await session.execute(
                    sa_update(TurnMetricsRecord)
                    .where(TurnMetricsRecord.room_id == self._room_id)
                    .values(**row_data)
                )

        except Exception as exc:
            try:
                from logger import WARNING, logger as get_logger
                get_logger().logp(WARNING, f"⚠️ Failed to update turn metrics: {exc}")
            except Exception:
                pass


# ------------------------------------------------------------------
# Context-variable helpers
# ------------------------------------------------------------------

_turn_metrics_var: contextvars.ContextVar[Optional[TurnMetrics]] = contextvars.ContextVar(
    "turn_metrics", default=None
)


def set_turn_metrics(tm: TurnMetrics | None) -> None:
    _turn_metrics_var.set(tm)


def get_turn_metrics() -> TurnMetrics | None:
    return _turn_metrics_var.get()

