# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``workflow_postprocess_nodes``.

Covers the post-processing nodes wired into the unified graph:
``asp_solving_node``, ``viz_building_node``, ``feedback_node``
(including the ``#bypass_feedback`` early return),
``format_feedback`` and the two remaining conditional
routers (``route_to_asp``, ``route_to_viz``).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from llm_processing.graphs import workflow_postprocess_nodes as ppn
from llm_processing.graphs.workflow_state import WorkflowState
from shared.llm_config import LLMConfig


# Per-test RunnableConfig — every node call now reads
# `config.configurable.llm_config`. The provider drives which yaml is
# loaded by `get_call_config`; tests monkeypatch that helper directly so
# the fake api_key here never reaches a provider SDK.
_FAKE_LLM_CONFIG = LLMConfig(provider="google_genai", api_key="fake-test-key")
_FAKE_RUNNABLE_CONFIG = {"configurable": {"llm_config": _FAKE_LLM_CONFIG}}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(
    *,
    xml_output: str = "<visuSpecAI/>",
    dynamic_asp_facts: list | None = None,
    feedback_material: dict | None = None,
    raw_user_input: str = "show data",
    message_history: list | None = None,
    list_steps: list | None = None,
    is_api: bool = False,
) -> WorkflowState:
    state = WorkflowState()
    state.input = {
        "raw_user_input": raw_user_input,
        "owner_id": "owner",
        "room_id": "room",
        "user_id": "user",
        "room_token": "token",
        "message_history": message_history or [],
        "is_api": is_api,
    }
    state.processing = {
        "xml_output": xml_output,
        "dynamic_asp_facts": dynamic_asp_facts or [],
        "feedback_material": feedback_material or {},
        "list_steps": list_steps or [],
    }
    return state


class _MixinHost(ppn.PostprocessNodesMixin):
    """Plain host class exposing the mixin methods for unit testing."""

    def __init__(self, db=None, llm_manager=None, http_client=None):
        self.db = db
        self.llm_manager = llm_manager
        self.http_client = http_client


# ---------------------------------------------------------------------------
# Utility tests
# ---------------------------------------------------------------------------


class TestConvertFeedbackToHtml:
    def test_plain_markdown_paragraph(self):
        out = ppn.convert_feedback_to_html("hello **world**")
        assert "<strong>world</strong>" in out

    def test_marker_substitution(self):
        out = ppn.convert_feedback_to_html("See {mark:Point} on the chart")
        assert '<span class="highlight_mark">Point</span>' in out

    def test_channel_marker(self):
        out = ppn.convert_feedback_to_html("Use {channel:x}")
        assert '<span class="highlight_channels">x</span>' in out

    def test_literal_newline_normalized(self):
        out = ppn.convert_feedback_to_html("line1\\nline2")
        assert "line1" in out and "line2" in out


# ---------------------------------------------------------------------------
# asp_solving_node (reads canonical xml_output / dynamic_asp_facts)
# ---------------------------------------------------------------------------


class TestAspSolvingNode:
    def test_success_path(self, monkeypatch):
        monkeypatch.setattr(
            ppn, "enhance_specifications_xml",
            lambda *a, **k: (True, "asp log ok", False),
        )
        monkeypatch.setattr(
            ppn, "XMLFileBuilder",
            lambda location: SimpleNamespace(xml_filepath=f"{location}/specifications.xml"),
        )
        monkeypatch.setattr(ppn, "ws_path", lambda o, r: f"/tmp/{o}/{r}")
        host = _MixinHost()
        state = _make_state()

        out = asyncio.run(host.asp_solving_node(state))

        assert out.processing["asp"] == {
            "success": True, "log": "asp log ok", "timed_out": False,
        }
        assert out.processing["feedback_material"]["ai_processing"] == "asp log ok"
        assert "asp_failed" not in out.processing["feedback_material"]

    def test_timeout_sets_timed_out_flag(self, monkeypatch):
        async def _raise_timeout(coro, timeout):
            coro.close()
            raise asyncio.TimeoutError()
        monkeypatch.setattr(asyncio, "wait_for", _raise_timeout)
        monkeypatch.setattr(
            ppn, "XMLFileBuilder",
            lambda location: SimpleNamespace(xml_filepath=f"{location}/spec.xml"),
        )
        monkeypatch.setattr(ppn, "ws_path", lambda o, r: f"/tmp/{o}/{r}")
        host = _MixinHost()
        state = _make_state()

        out = asyncio.run(host.asp_solving_node(state))

        assert out.processing["asp"]["success"] is False
        assert out.processing["asp"]["timed_out"] is True
        assert "took too long" in out.processing["asp"]["log"]
        assert out.processing["feedback_material"]["asp_failed"] is True

    def test_unexpected_error_is_caught(self, monkeypatch):
        def _boom(*a, **k):
            raise RuntimeError("kaboom")
        monkeypatch.setattr(ppn, "enhance_specifications_xml", _boom)
        monkeypatch.setattr(
            ppn, "XMLFileBuilder",
            lambda location: SimpleNamespace(xml_filepath=f"{location}/spec.xml"),
        )
        monkeypatch.setattr(ppn, "ws_path", lambda o, r: f"/tmp/{o}/{r}")
        host = _MixinHost()
        state = _make_state()

        out = asyncio.run(host.asp_solving_node(state))

        assert out.processing["asp"]["success"] is False
        assert out.processing["asp"]["timed_out"] is False
        assert "kaboom" in out.processing["asp"]["log"]
        assert out.processing["feedback_material"]["asp_failed"] is True

    def test_unsat_surfaces_failure_flag(self, monkeypatch):
        monkeypatch.setattr(
            ppn, "enhance_specifications_xml",
            lambda *a, **k: (False, "UNSAT", False),
        )
        monkeypatch.setattr(
            ppn, "XMLFileBuilder",
            lambda location: SimpleNamespace(xml_filepath=f"{location}/spec.xml"),
        )
        monkeypatch.setattr(ppn, "ws_path", lambda o, r: f"/tmp/{o}/{r}")
        host = _MixinHost()
        state = _make_state()

        out = asyncio.run(host.asp_solving_node(state))

        assert out.processing["asp"]["success"] is False
        assert out.processing["feedback_material"]["asp_failed"] is True
        assert out.processing["feedback_material"]["ai_processing"] == "UNSAT"


# ---------------------------------------------------------------------------
# viz_building_node
# ---------------------------------------------------------------------------


class TestVizBuildingNode:
    def test_ok_persists_viz_summary(self, monkeypatch):
        async def fake_build(*a, **k):
            return {
                "status": "ok",
                "viz_file": "my_viz.json",
                "viz_summary": {"frames": 1, "n_rows": 42},
            }
        monkeypatch.setattr(ppn, "build_viz_via_server", fake_build)
        monkeypatch.setattr(ppn, "ws_path", lambda o, r: f"/tmp/{o}/{r}")
        wrote = {}
        monkeypatch.setattr(
            ppn, "write_metadata",
            lambda o, r, payload: wrote.update(payload),
        )

        host = _MixinHost(http_client=MagicMock())
        state = _make_state()
        out = asyncio.run(host.viz_building_node(state))

        assert out.processing["viz_build"]["status"] == "ok"
        assert out.processing["viz_build"]["viz_file"] == "my_viz.json"
        assert "viz_summary" in out.processing["feedback_material"]
        assert "frames" in out.processing["feedback_material"]["viz_summary"]
        assert "last_viz_summary" in wrote

    def test_error_status_records_rendering_error(self, monkeypatch):
        async def fake_build(*a, **k):
            return {"status": "error", "message": "viz server unreachable"}
        monkeypatch.setattr(ppn, "build_viz_via_server", fake_build)
        monkeypatch.setattr(ppn, "ws_path", lambda o, r: f"/tmp/{o}/{r}")
        monkeypatch.setattr(ppn, "write_metadata", lambda *a, **k: None)

        host = _MixinHost(http_client=MagicMock())
        state = _make_state()
        out = asyncio.run(host.viz_building_node(state))

        assert out.processing["viz_build"]["status"] == "error"
        assert out.processing["viz_build"]["viz_file"] is None
        fm = out.processing["feedback_material"]
        assert "viz_rendering_error" in fm
        assert "viz server unreachable" in fm["viz_rendering_error"]


# ---------------------------------------------------------------------------
# format_feedback
# ---------------------------------------------------------------------------


class TestPostFeedbackHtmlInjection:
    def test_plain_text_no_viz(self):
        host = _MixinHost()
        state = _make_state(feedback_material={"ai_processing": "done"})
        state.processing["feedback_text"] = "**hi**"
        state.processing["viz_build"] = {"status": "error", "viz_file": None}
        out = host.format_feedback(state)
        resp = out.output["response"]
        assert "<strong>hi</strong>" in resp["text"]
        assert resp["suggestions"] == []

    def test_viz_thumbnail_replaces_placeholder(self):
        host = _MixinHost()
        state = _make_state(feedback_material={"ai_processing": "done"})
        state.processing["feedback_text"] = "Here: {visualization_placeholder}"
        state.processing["viz_build"] = {
            "status": "ok", "viz_file": "foo.json", "viz_summary": {}, "error": None,
        }
        out = host.format_feedback(state)
        text = out.output["response"]["text"]
        assert "{visualization_placeholder}" not in text
        assert "viz-thumbnail-btn" in text
        assert "history-anchor" in text

    def test_viz_thumbnail_appended_when_no_placeholder(self):
        host = _MixinHost()
        state = _make_state(feedback_material={"ai_processing": "done"})
        state.processing["feedback_text"] = "Hello"
        state.processing["viz_build"] = {
            "status": "ok", "viz_file": "foo.json", "viz_summary": {}, "error": None,
        }
        out = host.format_feedback(state)
        text = out.output["response"]["text"]
        assert "viz-thumbnail-btn" in text
        assert "history-export-dashboard" in text

    def test_color_palette_suggestion_from_llm_config(self):
        host = _MixinHost()
        state = _make_state(feedback_material={"color_palette_request": True})
        state.processing["feedback_text"] = "choose a palette"
        state.processing["viz_build"] = {"status": "error", "viz_file": None}
        state.processing["color_palette_config"] = {
            "name": "sunset",
            "type": "SEQUENTIAL",
            "breaks": [{"position": 0.0, "color": "#FF0000", "interpolation": "linear"}],
            "button_text": "🎨 Sunset",
        }
        out = host.format_feedback(state)
        sugg = out.output["response"]["suggestions"]
        assert len(sugg) == 1
        assert sugg[0]["type"] == "color_palette"
        assert sugg[0]["config"]["name"] == "sunset"

    def test_color_palette_fallback_when_no_config(self):
        host = _MixinHost()
        state = _make_state(feedback_material={"color_palette_request": True})
        state.processing["feedback_text"] = "here"
        state.processing["viz_build"] = {"status": "error", "viz_file": None}
        state.processing["color_palette_config"] = None
        out = host.format_feedback(state)
        sugg = out.output["response"]["suggestions"]
        assert sugg[0]["config"]["name"] == "custom_palette"

    def test_selection_prompt_passthrough(self):
        host = _MixinHost()
        state = _make_state(feedback_material={"ai_processing": "done"})
        state.processing["feedback_text"] = "choose"
        state.processing["viz_build"] = {"status": "error", "viz_file": None}
        state.processing["selection_prompt"] = {
            "prompt_id": "p1",
            "prompt": "Pick one",
            "options": [{"id": "a", "label": "A", "description": ""}],
        }
        out = host.format_feedback(state)
        assert "selection_prompt" in out.output["response"]
        assert out.output["response"]["selection_prompt"]["prompt_id"] == "p1"


# ---------------------------------------------------------------------------
# feedback_node — bypass early return
# ---------------------------------------------------------------------------


class TestFeedbackNodeBypass:
    def test_bypass_writes_feedback_text_without_llm(self):
        host = _MixinHost(db=MagicMock(), llm_manager=MagicMock())
        state = _make_state(raw_user_input="do it #bypass_feedback")
        out = asyncio.run(host.feedback_node(state, _FAKE_RUNNABLE_CONFIG))
        # bypass writes the canned text to feedback_text; format_feedback
        # then wraps it in HTML on the unconditional downstream edge.
        assert out.processing.get("feedback_text") == "Feedback bypassed as per user request."
        assert out.processing.get("color_palette_config") is None
        assert out.processing.get("selection_prompt") is None
        # The LLM must not have been called on the bypass path.
        assert not host.llm_manager.method_calls


# ---------------------------------------------------------------------------
# feedback_node — normal path
# ---------------------------------------------------------------------------


class TestFeedbackNode:
    def test_happy_path_writes_processing_slots(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ppn, "ws_path", lambda o, r: tmp_path)
        monkeypatch.setattr(ppn, "read_metadata", lambda *a, **k: {})
        monkeypatch.setattr(ppn, "format_message_history", lambda msgs: "")
        monkeypatch.setattr(ppn, "clean_raw_feedback_output", lambda x: x)
        monkeypatch.setattr(ppn, "get_call_config", lambda name, cfg: (
            _FAKE_LLM_CONFIG,
            {"model": "fake", "temperature": 0.1,
             "thinking_level": None, "include_thoughts": False},
        ))

        class _FakeChatTemplate:
            def with_config(self, *a, **k): return self
        class _FakeFM:
            def build(self, *a, **k):
                return (_FakeChatTemplate(), {"personality_placeholder": "", "feedback_material": ""})
        monkeypatch.setattr(ppn, "FeedbackMessage", lambda: _FakeFM())

        fake_response = SimpleNamespace(
            feedback_text="Nice!",
            color_palette_config=None,
            selection_prompt=None,
        )
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value=fake_response)
        db = MagicMock()
        db.get_user_tone = AsyncMock(return_value="friendly")

        host = _MixinHost(db=db, llm_manager=llm)
        state = _make_state(
            feedback_material={"ai_processing": "done"},
            list_steps=["viz_rendering"],
        )
        out = asyncio.run(host.feedback_node(state, _FAKE_RUNNABLE_CONFIG))

        assert out.processing["feedback_text"] == "Nice!"
        assert out.processing["color_palette_config"] is None
        assert out.processing["selection_prompt"] is None
        llm.ainvoke.assert_awaited_once()

    def test_llm_failure_uses_question_answer_shortcut(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ppn, "ws_path", lambda o, r: tmp_path)
        monkeypatch.setattr(ppn, "read_metadata", lambda *a, **k: {})
        monkeypatch.setattr(ppn, "format_message_history", lambda msgs: "")
        monkeypatch.setattr(ppn, "get_call_config", lambda name, cfg: (
            _FAKE_LLM_CONFIG,
            {"model": "fake", "temperature": 0.1,
             "thinking_level": None, "include_thoughts": False},
        ))

        class _FakeChatTemplate:
            def with_config(self, *a, **k): return self
        class _FakeFM:
            def build(self, *a, **k):
                return (_FakeChatTemplate(), {"personality_placeholder": "", "feedback_material": ""})
        monkeypatch.setattr(ppn, "FeedbackMessage", lambda: _FakeFM())

        llm = MagicMock()
        llm.ainvoke = AsyncMock(side_effect=RuntimeError("boom"))
        db = MagicMock()
        db.get_user_tone = AsyncMock(return_value="friendly")

        host = _MixinHost(db=db, llm_manager=llm)
        state = _make_state(
            feedback_material={
                "question_answer": "42",
                "user_question": "What is the answer?",
            },
            list_steps=["user_question"],
        )
        out = asyncio.run(host.feedback_node(state, _FAKE_RUNNABLE_CONFIG))

        assert out.processing["feedback_text"] == "42"

    def test_empty_feedback_material_is_noop(self):
        host = _MixinHost(db=MagicMock(), llm_manager=MagicMock())
        state = _make_state(feedback_material={})
        out = asyncio.run(host.feedback_node(state, _FAKE_RUNNABLE_CONFIG))
        assert "feedback_text" not in out.processing


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------


class TestRouters:
    def test_route_to_asp_skips_when_xml_empty(self):
        state = _make_state(xml_output="")
        assert ppn.route_to_asp(state) == "feedback_node"

    def test_route_to_asp_skips_when_only_whitespace(self):
        state = _make_state(xml_output="   \n  ")
        assert ppn.route_to_asp(state) == "feedback_node"

    def test_route_to_asp_runs_asp_when_xml_present(self):
        state = _make_state(xml_output="<visuSpecAI/>")
        assert ppn.route_to_asp(state) == "asp_solving_node"

    def test_route_to_viz_skips_on_asp_failure(self):
        state = _make_state()
        state.processing["asp"] = {"success": False, "log": "nope", "timed_out": False}
        assert ppn.route_to_viz(state) == "feedback_node"

    def test_route_to_viz_proceeds_on_asp_success_web(self):
        state = _make_state(is_api=False)
        state.processing["asp"] = {"success": True, "log": "ok", "timed_out": False}
        assert ppn.route_to_viz(state) == "viz_building_node"

    def test_route_to_viz_ends_on_asp_success_sdk(self):
        state = _make_state(is_api=True)
        state.processing["asp"] = {"success": True, "log": "ok", "timed_out": False}
        assert ppn.route_to_viz(state) == "__end__"


# ---------------------------------------------------------------------------
# UserRequest graph integration — topology wiring
# ---------------------------------------------------------------------------


class TestGraphPostprocessWiring:
    """Verify that the compiled UserRequest graph actually wires ASP + viz + feedback."""

    def _compile(self):
        from llm_processing.graphs.workflow_request import UserRequest
        graph = UserRequest(
            db=AsyncMock(), llm_manager=MagicMock(),
            http_client=AsyncMock(), checkpointer=None,
        )
        return graph.compile()

    def test_post_processing_nodes_registered(self):
        compiled = self._compile()
        node_names = set(compiled.nodes.keys())
        assert {
            "asp_solving_node",
            "viz_building_node",
            "feedback_node",
            "format_feedback",
            "trigger_choregraph_run_node",
        } <= node_names

    def test_asp_routes_to_viz_or_feedback_or_end(self):
        compiled = self._compile()
        branches = compiled.builder.branches
        assert "asp_solving_node" in branches
        targets = set()
        for branch in branches["asp_solving_node"].values():
            ends = branch.ends or {}
            targets.update(ends.values())
        # route_to_viz can produce any of these three
        assert "viz_building_node" in targets
        assert "feedback_node" in targets
