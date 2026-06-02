# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for TurnMetrics — per-turn measurement accumulation and formatting."""

from llm_processing.turn_metrics import (
    TurnMetrics,
    StepRecord,
    set_turn_metrics,
    get_turn_metrics,
)


class TestRecord:
    def test_accumulates_steps(self):
        tm = TurnMetrics()
        tm.record("Step A", 1.5, {"input_tokens": 100, "output_tokens": 50})
        tm.record("Step B", 2.0, {"input_tokens": 200, "output_tokens": 80})
        assert len(tm.steps) == 2
        assert tm.steps[0].label == "Step A"
        assert tm.steps[0].elapsed_s == 1.5
        assert tm.steps[0].input_tokens == 100
        assert tm.steps[1].output_tokens == 80

    def test_handles_missing_usage_keys(self):
        tm = TurnMetrics()
        tm.record("Step", 1.0, {})
        assert tm.steps[0].input_tokens == 0
        assert tm.steps[0].cached_tokens == 0
        assert tm.steps[0].output_tokens == 0
        assert tm.steps[0].thinking_tokens == 0

    def test_handles_none_in_nested_dicts(self):
        tm = TurnMetrics()
        tm.record("Step", 1.0, {
            "input_tokens": None,
            "input_token_details": None,
            "output_token_details": {"reasoning": None},
        })
        assert tm.steps[0].input_tokens == 0
        assert tm.steps[0].cached_tokens == 0
        assert tm.steps[0].thinking_tokens == 0

    def test_extracts_cached_and_thinking_tokens(self):
        tm = TurnMetrics()
        tm.record("Step", 1.0, {
            "input_tokens": 500,
            "output_tokens": 200,
            "input_token_details": {"cache_read": 300},
            "output_token_details": {"reasoning": 50},
        })
        assert tm.steps[0].cached_tokens == 300
        assert tm.steps[0].thinking_tokens == 50


class TestRecordRetries:
    def test_stores_retries(self):
        tm = TurnMetrics()
        tm.record_retries("XML Generation", 2)
        assert tm.node_retries["XML Generation"] == 2


class TestFormatTable:
    def test_no_steps(self):
        tm = TurnMetrics()
        result = tm.format_table()
        assert isinstance(result, str)
        assert len(result) > 0  # should return a message, not empty

    def test_single_step(self):
        tm = TurnMetrics()
        tm.record("Test Step", 1.23, {"input_tokens": 100, "output_tokens": 50})
        result = tm.format_table()
        assert "Test Step" in result
        assert "1.23" in result
        assert "100" in result

    def test_with_retries_info(self):
        tm = TurnMetrics()
        tm.record("Step", 1.0, {"input_tokens": 10, "output_tokens": 5})
        tm.record_retries("XML Generation", 2)
        result = tm.format_table()
        assert "XML Generation" in result
        assert "2" in result

    def test_totals_correct(self):
        tm = TurnMetrics()
        tm.record("A", 1.0, {"input_tokens": 100, "output_tokens": 50})
        tm.record("B", 2.0, {"input_tokens": 200, "output_tokens": 80})
        result = tm.format_table()
        assert "300" in result  # total input tokens
        assert "130" in result  # total output tokens


class TestSetContext:
    def test_sets_ids(self):
        tm = TurnMetrics()
        tm.set_context(room_id="r1", owner_id="o1", user_id="u1")
        assert tm._room_id == "r1"
        assert tm._owner_id == "o1"
        assert tm._user_id == "u1"

    def test_defaults_to_web_source(self):
        tm = TurnMetrics()
        tm.set_context(room_id="r1", owner_id="o1", user_id="u1")
        assert tm._source == "web"

    def test_sdk_source(self):
        tm = TurnMetrics()
        tm.set_context(room_id="api-123", owner_id="o1", user_id="api", source="sdk")
        assert tm._source == "sdk"


class TestRowDataBuilding:
    """Test that persist_to_db would build correct row data for both web and SDK flows."""

    def _build_row_data(self, tm: TurnMetrics) -> dict:
        """Extract the row_data dict that persist_to_db would insert.

        Mirrors the logic in persist_to_db without hitting the database.
        """
        from collections import defaultdict
        from llm_processing.turn_metrics import _LABEL_MAP, _ATTEMPT_SUFFIXES

        row_data = {
            "room_id": tm._room_id,
            "owner_id": tm._owner_id,
            "user_id": tm._user_id,
            "source": tm._source,
        }

        prefix_steps: dict[str, list] = defaultdict(list)
        for step in tm.steps:
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
                    row_data[f"{col_prefix}_output_tokens"] = step.output_tokens
            else:
                step = steps_list[0]
                row_data[f"{prefix}_elapsed_s"] = step.elapsed_s
                row_data[f"{prefix}_input_tokens"] = step.input_tokens
                row_data[f"{prefix}_output_tokens"] = step.output_tokens

        row_data["planning_retries"] = tm.node_retries.get("Planning Transformation", 0)
        row_data["xml_gen_retries"] = tm.node_retries.get("XML Generation", 0)
        row_data["total_elapsed_s"] = sum(s.elapsed_s for s in tm.steps)
        row_data["total_input_tokens"] = sum(s.input_tokens for s in tm.steps)
        row_data["total_output_tokens"] = sum(s.output_tokens for s in tm.steps)

        return row_data

    def test_web_flow_single_row(self):
        """Web chat: all steps recorded in one TurnMetrics, one INSERT."""
        tm = TurnMetrics()
        tm.set_context(room_id="room-1", owner_id="owner-1", user_id="user-1")

        # Classification
        tm.record("Entry Point Message Type Classification", 0.5,
                  {"input_tokens": 100, "output_tokens": 20})
        # Planning (1 attempt)
        tm.record("Transformation XML Generation", 2.0,
                  {"input_tokens": 500, "output_tokens": 200})
        # XML gen (1 attempt)
        tm.record("XML Generation Node with Cache", 3.0,
                  {"input_tokens": 800, "output_tokens": 400})
        # Exclusion
        tm.record("Exclusion Processing Node", 0.3,
                  {"input_tokens": 50, "output_tokens": 10})

        row = self._build_row_data(tm)

        assert row["source"] == "web"
        assert row["room_id"] == "room-1"
        # Classification
        assert row["entry_classif_elapsed_s"] == 0.5
        assert row["entry_classif_input_tokens"] == 100
        # Planning
        assert row["planning_1st_elapsed_s"] == 2.0
        assert row["planning_1st_input_tokens"] == 500
        # XML gen
        assert row["xml_gen_1st_elapsed_s"] == 3.0
        assert row["xml_gen_1st_input_tokens"] == 800
        # Exclusion
        assert row["exclusion_elapsed_s"] == 0.3
        # Totals
        assert row["total_elapsed_s"] == 5.8
        assert row["total_input_tokens"] == 1450
        assert row["total_output_tokens"] == 630

    def test_sdk_call1_inserts_planning_metrics(self):
        """SDK call 1 (/processing/plan): classification + planning only."""
        tm = TurnMetrics()
        tm.set_context(room_id="api-abc", owner_id="owner-1", user_id="api", source="sdk")

        tm.record("Entry Point Message Type Classification", 0.4,
                  {"input_tokens": 90, "output_tokens": 15})
        tm.record("Transformation XML Generation", 1.8,
                  {"input_tokens": 450, "output_tokens": 180})
        tm.record_retries("Planning Transformation", 1)

        row = self._build_row_data(tm)

        assert row["source"] == "sdk"
        assert row["room_id"] == "api-abc"
        assert row["entry_classif_elapsed_s"] == 0.4
        assert row["planning_1st_elapsed_s"] == 1.8
        assert row["planning_retries"] == 1
        # No xml_gen or exclusion columns
        assert "xml_gen_1st_elapsed_s" not in row
        assert "exclusion_elapsed_s" not in row
        # Totals reflect only call 1 steps
        assert row["total_elapsed_s"] == 2.2
        assert row["total_input_tokens"] == 540

    def test_sdk_call2_builds_viz_metrics(self):
        """SDK call 2 (/visualization/generate): xml_gen + exclusion only."""
        tm = TurnMetrics()
        tm.set_context(room_id="api-abc", owner_id="owner-1", user_id="api", source="sdk")

        tm.record("XML Generation Node with Cache", 2.5,
                  {"input_tokens": 700, "output_tokens": 350})
        tm.record("Exclusion Processing Node", 0.2,
                  {"input_tokens": 40, "output_tokens": 8})

        row = self._build_row_data(tm)

        assert row["xml_gen_1st_elapsed_s"] == 2.5
        assert row["xml_gen_1st_input_tokens"] == 700
        assert row["exclusion_elapsed_s"] == 0.2
        # No planning columns
        assert "entry_classif_elapsed_s" not in row
        assert "planning_1st_elapsed_s" not in row

    def test_planning_with_retries(self):
        """Planning with 2 attempts produces 1st and 2nd columns."""
        tm = TurnMetrics()
        tm.set_context(room_id="r1", owner_id="o1", user_id="u1")

        tm.record("Transformation XML Generation", 2.0,
                  {"input_tokens": 500, "output_tokens": 200})
        tm.record("Transformation XML Generation", 1.5,
                  {"input_tokens": 500, "output_tokens": 180})
        tm.record_retries("Planning Transformation", 1)

        row = self._build_row_data(tm)

        assert row["planning_1st_elapsed_s"] == 2.0
        assert row["planning_2nd_elapsed_s"] == 1.5
        assert row["planning_retries"] == 1


class TestContextVar:
    def test_set_and_get(self):
        tm = TurnMetrics()
        set_turn_metrics(tm)
        assert get_turn_metrics() is tm

    def test_default_none(self):
        set_turn_metrics(None)
        assert get_turn_metrics() is None
