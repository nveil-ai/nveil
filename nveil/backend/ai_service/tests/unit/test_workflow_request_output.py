# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the shortcut-expansion node.

``OutputNodesMixin`` now only hosts ``expand_shortcut_node`` (the
``prepare_*_processing_state`` rewiring nodes are gone — each piece of
``feedback_material`` is now written by the node that actually produces
it, not by a dedicated assembly pass).

Also hosts the strict-mode guard for every ``response_schema`` used
across the LLM-calling nodes (see ``TestResponseSchemasStrictCompatible``).
"""

import pathlib

import pytest

from llm_processing.graphs.workflow_request_output import OutputNodesMixin
from llm_processing.graphs.workflow_state import WorkflowState
from llm_processing.graphs.workflow_request_classify import (
    LLMResponseClassification, ListLLMResponseClassification,
)
from llm_processing.graphs.workflow_request_nodes import (
    AdditionalInfoType, Exclusion, Exclusions, FallbackTransformationOutput,
    MessageTypeClassification, Plan, QuestionType, TransformationOutput,
)
from llm_processing.graphs.workflow_postprocess_nodes import (
    ColorPaletteBreak, ColorPaletteConfig, FeedbackStructure,
    SelectionOption, SelectionPromptModel,
)
from viz_file_utils.characterization import CSVFileStruct


class _Node(OutputNodesMixin):
    """Minimal subclass so we can call the mixin method in isolation."""


def _fresh_state(**processing_overrides):
    state = WorkflowState()
    state.input = {
        "raw_user_input": "",
        "is_an_upload_message": False,
        "owner_id": "u1",
        "room_id": "r1",
    }
    state.processing = {
        "current_language": "english",
        "feedback_material": {"language": "english", "user_last_message": ""},
        "xml_output": "",
        "dynamic_asp_facts": [],
        "list_steps": [],
        **processing_overrides,
    }
    state.output = {}
    return state


class TestExpandShortcutNode:
    def test_question_nveil_seeds_user_question(self):
        state = _fresh_state()
        state.input["raw_user_input"] = "#nveil#question_nveil What does this mean?"
        result = _Node().expand_shortcut_node(state)
        assert result.processing["user_question"] == {
            "company_related": "What does this mean?",
            "other": None,
        }
        assert result.processing["list_steps"] == ["user_question"]
        assert result.processing["feedback_material"]["user_question"] == result.processing["user_question"]
        assert result.output == {}

    def test_question_other_seeds_user_question(self):
        state = _fresh_state()
        state.input["raw_user_input"] = "#nveil#question_other general question"
        result = _Node().expand_shortcut_node(state)
        assert result.processing["user_question"]["other"] == "general question"
        assert result.processing["list_steps"] == ["user_question"]

    def test_previous_xml_missing_file(self):
        """When specificationsBeforeAI.xml is missing, xml_output stays empty
        but list_steps still carries visualization_request so the routing
        reaches ASP (where route_to_asp will short-circuit to feedback)."""
        state = _fresh_state()
        state.input["raw_user_input"] = "#nveil#previous_xml"
        state.processing["workspace_path"] = pathlib.Path("/nonexistent/workspace")
        result = _Node().expand_shortcut_node(state)
        assert result.processing["list_steps"] == ["visualization_request"]
        assert result.processing["xml_output"] == ""
        assert result.output == {}

    def test_no_shortcut_is_noop(self):
        state = _fresh_state()
        state.input["raw_user_input"] = "just a regular message"
        result = _Node().expand_shortcut_node(state)
        assert result.processing["xml_output"] == ""
        assert result.processing["list_steps"] == []


# ---------------------------------------------------------------------------
# Strict-mode guard for every Pydantic response_schema used by LLM nodes
# ---------------------------------------------------------------------------

# Every class here is passed as ``response_schema`` to
# ``llm_manager.ainvoke(...)`` somewhere in the codebase. If any of them stops
# being OpenAI-strict-compatible, both ``method="json_schema"`` and
# ``method="function_calling"`` degrade silently (downgraded sampling, or
# LangChain refusing to auto-parse "not strict" tools) — and local quantized
# models stop producing valid output entirely. Keep this list in sync.
ALL_RESPONSE_SCHEMAS = [
    # workflow_request_nodes
    AdditionalInfoType, QuestionType, MessageTypeClassification,
    Exclusion, Exclusions, Plan, TransformationOutput,
    FallbackTransformationOutput,
    # workflow_postprocess_nodes
    ColorPaletteBreak, ColorPaletteConfig, SelectionOption,
    SelectionPromptModel, FeedbackStructure,
    # workflow_request_classify
    LLMResponseClassification, ListLLMResponseClassification,
    # viz_file_utils.characterization
    CSVFileStruct,
]

# JSON Schema keywords that OpenAI strict mode rejects (cannot be compiled
# into a deterministic GBNF). `format` is intentionally NOT listed: a
# handful of formats are tolerated and we don't currently use any — if a
# future schema needs one, the call will fail loudly enough on its own.
_FORBIDDEN_KEYWORDS = frozenset({
    "oneOf", "not", "patternProperties", "propertyNames",
    "unevaluatedProperties", "unevaluatedItems",
    "pattern", "minLength", "maxLength",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "multipleOf", "minItems", "maxItems", "uniqueItems",
})


def _walk_schema_nodes(node):
    """Yield every dict node nested inside a JSON Schema document."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk_schema_nodes(v)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_schema_nodes(item)


def _strict_violations(schema: dict) -> list[str]:
    """Return a human-readable list of strict-mode violations in `schema`."""
    errors: list[str] = []
    for sub in _walk_schema_nodes(schema):
        # Object schemas: must forbid extras AND list every property in required
        if sub.get("type") == "object":
            additional = sub.get("additionalProperties")
            if additional is not False:
                errors.append(
                    f"object missing `additionalProperties: false` "
                    f"(got {additional!r}); properties="
                    f"{sorted(sub.get('properties', {}))}"
                )
            props = set(sub.get("properties", {}))
            required = set(sub.get("required", []))
            missing = sorted(props - required)
            if missing:
                errors.append(
                    f"object properties not listed in `required`: {missing}"
                )
        # Pydantic emits a `default` key whenever a field has one, which
        # tells JSON Schema "this property is optional" — strict mode bans it.
        if "default" in sub:
            errors.append(
                f"`default` value present (forbidden — implies optional): "
                f"{sub['default']!r}"
            )
        # Constructs the OpenAI strict sampler cannot grammaticalize.
        for kw in _FORBIDDEN_KEYWORDS:
            if kw in sub:
                errors.append(f"forbidden keyword `{kw}`={sub[kw]!r}")
    return errors


class TestResponseSchemasStrictCompatible:
    """All LLM ``response_schema`` classes must pass OpenAI strict-mode rules.

    Why this guards correctness across providers — not just OpenAI:

    * ``with_structured_output(method="json_schema")`` ships the
      Pydantic-generated schema with ``strict: true`` by default. Providers
      that don't accept the violations (OpenAI, recent Ollama, llama.cpp via
      grammar compilation) silently downgrade to non-constrained sampling,
      which on quantized local models reliably produces free text instead
      of JSON.
    * ``with_structured_output(method="function_calling")`` refuses to
      auto-parse "not strict" tool definitions ("Only `strict` function
      tools can be auto-parsed") — the fallback method we rely on when
      json_schema fails ponctually.

    Both failure modes are invisible until a real call happens. This test
    catches schema regressions at CI time instead.
    """

    @pytest.mark.parametrize(
        "schema_cls", ALL_RESPONSE_SCHEMAS, ids=lambda c: c.__name__,
    )
    def test_schema_is_strict_compatible(self, schema_cls):
        schema = schema_cls.model_json_schema()
        violations = _strict_violations(schema)
        assert not violations, (
            f"{schema_cls.__name__} is not OpenAI-strict-compatible:\n  - "
            + "\n  - ".join(violations)
        )
