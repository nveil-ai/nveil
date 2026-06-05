# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Post-processing nodes for the unified LangGraph workflow.

This module hosts:

* Module-level utilities previously living in ``ai_server.py``
  (``inject_active_palette``, ``enhance_specifications_xml``,
  ``convert_feedback_to_html``, ``build_viz_via_server``).
* ``PostprocessNodesMixin`` — a mixin class contributing LangGraph nodes
  for ASP solving, viz building, feedback generation, HTML injection.
  ``#bypass_feedback`` is handled as an early return inside
  ``feedback_node`` (no separate terminal node).
* Conditional routers used to wire those nodes together
  (``route_to_asp``, ``route_to_viz``).

State convention (see ``memory/convention_workflow_state.md``):
``state.output`` contains ONLY the final response returned to the
client; all intermediates (feedback_material, ASP logs, viz_build
results, feedback_text, color_palette_config, selection_prompt, …) live
in ``state.processing``.
"""

from __future__ import annotations

import asyncio
import html
import json
import os
import pathlib
import re
from typing import Any

import httpx
import mistune
from lxml import etree as ET
from pydantic import BaseModel, ConfigDict, Field
from typing import List

from dive.asp import ASPSolver
from dive.xml import parse_from_file, save_to_file
from logger import DEBUG, ERROR, INFO, WARNING, logger
from shared.security import safe_path, sanitize_filename
from shared.workspace import read_metadata, workspace_path as ws_path, write_metadata
from choregraph.parser import ChoregraphSpecParser
from choregraph.metadata import Metadata
from viz_file_utils.utils.viz_xml_processor import XMLFileBuilder

from ..config import SERVER_HOST, SERVER_PORT
from ..node_config import get_call_config
from ..prompt import FeedbackMessage
from .workflow import tag_current_trace
from .workflow_utils import clean_raw_feedback_output, format_message_history


# ---------------------------------------------------------------------------
# Pydantic response schemas for feedback_node
# ---------------------------------------------------------------------------


class ColorPaletteBreak(BaseModel):
    model_config = ConfigDict(extra="forbid")
    position: float = Field(description="Position from 0.0 to 1.0")
    color: str = Field(description="Hex color like #FF0000")
    interpolation: str = Field(description="linear or step")


class ColorPaletteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(description="custom_palette")
    type: str = Field(description="SEQUENTIAL, DIVERGING, or QUALITATIVE")
    breaks: List[ColorPaletteBreak]
    button_text: str = Field(description="Short button label in user language")


class SelectionOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    label: str
    description: str | None


class SelectionPromptModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt_id: str
    prompt: str
    options: list[SelectionOption]


class FeedbackStructure(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feedback_text: str
    color_palette_config: ColorPaletteConfig | None
    selection_prompt: SelectionPromptModel | None


# ---------------------------------------------------------------------------
# Module-level utilities (migrated from ai_server.py)
# ---------------------------------------------------------------------------


def inject_active_palette(path: str, xml_processor: XMLFileBuilder) -> None:
    """Inject the active custom colour palette recorded in metadata.json."""
    try:
        tree = ET.parse(path)
        root = tree.getroot()

        metadata_path = safe_path(pathlib.Path(path).parent, "metadata.json")
        if not metadata_path.exists():
            return
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
        active_palette = metadata.get("active_color_palette")
        if not active_palette:
            return
        custom_palettes = metadata.get("custom_color_palettes")
        if not custom_palettes:
            return

        for palette in custom_palettes:
            if palette.get("name") != active_palette:
                continue
            xml_processor.inject_custom_palette(root, palette)
            xml_processor.indent(root)
            tree = ET.ElementTree(root)
            tree.write(path, encoding="utf-8", xml_declaration=True)
            logger().logp(INFO, "Custom color palette injected from metadata")
            return
    except Exception as e:
        logger().logp(WARNING, f"⚠️ Could not inject custom palette: {e}")


def enhance_specifications_xml(
    path: str,
    xml_processor: XMLFileBuilder,
    LLM_generated_xml_content: str,
    room_id: str,
    owner_id: str,
    dynamic_asp_facts: list,
):
    """Merge LLM output into specifications.xml and run the ASP solver.

    Returns ``(asp_success: bool, log: str, showErrorNotification: bool)``.
    """
    log = ""
    if not LLM_generated_xml_content or not LLM_generated_xml_content.strip():
        return True, log, False

    try:
        xml_processor.complete_xml_file_from_ai(path, LLM_generated_xml_content)
        inject_active_palette(path, xml_processor)
        vs = parse_from_file(path)

        backup_path = str(safe_path(pathlib.Path(path).parent, "specificationsBeforeAI.xml"))
        save_to_file(vs, backup_path)
        solver = ASPSolver()
        asp_success, asp_log = solver.asp_call(
            vs, path, debug_mode=False, extra_facts=dynamic_asp_facts,
            logger_fn=lambda level, msg: logger().logp(level, msg),
        )
        log += asp_log
        return asp_success, log, False
    except Exception as e:
        logger().logp(ERROR, e)
        p = pathlib.Path(path)
        backup = p.parent / "specificationsBeforeAI.xml"
        if backup.exists():
            if p.exists():
                p.unlink()
            backup.rename(p.parent / "specifications.xml")
        return False, log + f" Error during AI Enhancing steps: {e}", True


_md = mistune.create_markdown(escape=False, hard_wrap=True)
_MARKER_RE = re.compile(r"\{(mark|field|channel):(.+?)\}")
_MARKER_CSS = {
    "mark": "highlight_mark",
    "field": "highlight_field",
    "channel": "highlight_channels",
}


def convert_feedback_to_html(text: str) -> str:
    """Convert markdown + ``{marker:text}`` syntax to HTML."""
    text = text.replace("\\n", "\n")
    rendered = _md(text)

    def _replace(m):
        css = _MARKER_CSS.get(m.group(1), m.group(1))
        return f'<span class="{css}">{m.group(2)}</span>'

    return _MARKER_RE.sub(_replace, rendered)


async def post_stage_notification(
    http_client: httpx.AsyncClient,
    room_token: str,
    stage: str,
    label: str,
) -> None:
    """Fire-and-forget stage notification used by ASP/viz nodes."""
    if not room_token:
        return
    host_srv = SERVER_HOST or "localhost"
    try:
        await http_client.post(
            f"https://{host_srv}:{SERVER_PORT}/server/stage",
            json={"room_token": room_token, "stage": stage, "label": label},
            timeout=3.0,
        )
    except Exception:
        pass


async def build_viz_via_server(
    http_client: httpx.AsyncClient,
    xml_path: str,
    room_token: str,
    server_host: str | None = None,
    server_port: int = SERVER_PORT,
) -> dict:
    """POST /viz/send on the server proxy to render a visualization.

    Exceptions are converted into ``{"status": "error", "message": ...}``
    so callers never have to guard against network failures.
    """
    try:
        host = server_host or SERVER_HOST or "localhost"
        url = f"https://{host}:{server_port}/viz/send"
        trame_data = {
            "command": "build_viz",
            "xml_path": str(pathlib.Path(xml_path) / "specifications.xml"),
        }
        viz_cookies = {"room_token": room_token}
        resp = await http_client.post(
            url, json=trame_data, cookies=viz_cookies, timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger().logp(ERROR, f"Viz build error: {e}")
        return {"status": "error", "message": str(e)}


_VIZ_PLACEHOLDER_RE = re.compile(r"(<p>\s*)?\{visualization_placeholder\}(\s*</p>)?")


# ---------------------------------------------------------------------------
# Post-processing mixin — plugged into UserRequest via MRO in step 2.
# ---------------------------------------------------------------------------


class PostprocessNodesMixin:
    """LangGraph nodes that run after the main request graph.

    Designed to be mixed into a :class:`Workflow` subclass so that
    ``self.db``, ``self.llm_manager`` and ``self.http_client`` are
    available at runtime.
    """

    # ---- ASP -------------------------------------------------------------

    async def asp_solving_node(self, state):
        """Run ASP on the XML produced upstream.

        Reads ``state.processing["xml_output"]`` and
        ``state.processing["dynamic_asp_facts"]`` — the canonical keys
        written by ``xml_generation`` and ``classify_user_intention`` /
        ``exclusion_processing``. Writes
        ``state.processing.asp = {success, log, timed_out}`` and merges
        the log / failure flags into
        ``state.processing.feedback_material``. Never raises.
        """
        logger().logp(DEBUG, "[NODE] asp_solving_node entered")
        processing = state.processing or {}
        xml_output = processing.get("xml_output", "") or ""
        dynamic_asp_facts = processing.get("dynamic_asp_facts", []) or []

        feedback_material = dict(processing.get("feedback_material", {}) or {})

        owner_id = state.input.get("owner_id")
        room_id = state.input.get("room_id")
        room_token = state.input.get("room_token")
        workspace = ws_path(owner_id, room_id)
        xml_processor = XMLFileBuilder(location=str(workspace))

        await post_stage_notification(
            self.http_client, room_token, "solving_logic", "Solving logic constraints",
        )

        try:
            asp_success, log_asp, _show = await asyncio.wait_for(
                asyncio.to_thread(
                    enhance_specifications_xml,
                    xml_processor.xml_filepath,
                    xml_processor,
                    xml_output,
                    room_id,
                    owner_id,
                    dynamic_asp_facts,
                ),
                timeout=60.0,
            )
            asp_result = {"success": asp_success, "log": log_asp, "timed_out": False}
        except asyncio.TimeoutError:
            logger().logp(ERROR, "ASP solving timed out after 60 seconds.")
            asp_result = {
                "success": False,
                "log": (
                    "The visualization logic took too long to process. "
                    "If possible, try to be more specific in your request "
                    "to reduce the logic complexity."
                ),
                "timed_out": True,
            }
        except Exception as e:
            logger().logp(ERROR, f"Unexpected ASP error: {e}")
            asp_result = {
                "success": False,
                "log": f"Unexpected error during visualization logic solving: {e}",
                "timed_out": False,
            }

        feedback_material["ai_processing"] = asp_result["log"]
        if not asp_result["success"]:
            feedback_material["asp_failed"] = True

        state.processing["asp"] = asp_result
        state.processing["feedback_material"] = feedback_material
        return state

    # ---- Viz build -------------------------------------------------------

    async def viz_building_node(self, state):
        """Render the visualization via the server proxy.

        Writes ``state.processing.viz_build = {status, viz_file,
        viz_summary, error}`` and merges viz_summary / viz_rendering_error
        into ``state.processing.feedback_material``. Persists the last
        viz_summary in the workspace metadata for later question turns.
        """
        logger().logp(DEBUG, "[NODE] viz_building_node entered")
        processing = state.processing or {}
        feedback_material = dict(processing.get("feedback_material", {}) or {})

        owner_id = state.input.get("owner_id")
        room_id = state.input.get("room_id")
        room_token = state.input.get("room_token")
        workspace = ws_path(owner_id, room_id)

        await post_stage_notification(
            self.http_client, room_token, "viz_building", "Building visualization",
        )
        result = await build_viz_via_server(
            self.http_client, str(workspace), room_token,
        )

        if result.get("status") == "ok":
            viz_summary = result.get("viz_summary")
            viz_file = result.get("viz_file")
            viz_build = {
                "status": "ok",
                "viz_file": viz_file,
                "viz_summary": viz_summary,
                "error": None,
            }
            if viz_summary:
                summary_str = json.dumps(viz_summary, indent=2, default=str)
                feedback_material["viz_summary"] = summary_str
                try:
                    write_metadata(owner_id, room_id, {"last_viz_summary": summary_str})
                except Exception as e:
                    logger().logp(WARNING, f"Could not persist last_viz_summary: {e}")
        else:
            error_msg = result.get("error") or result.get("message") or result.get("details") or "Unknown error"
            viz_build = {
                "status": "error",
                "viz_file": None,
                "viz_summary": None,
                "error": error_msg,
            }
            feedback_material["viz_rendering_error"] = (
                f"The visualization rendering failed: {error_msg}"
            )

        state.processing["viz_build"] = viz_build
        state.processing["feedback_material"] = feedback_material
        return state

    # ---- Feedback --------------------------------------------------------

    async def feedback_node(self, state, config):
        """Ask the LLM for a textual feedback on the current turn.

        Reads ``state.processing.feedback_material`` / ``list_steps`` and
        writes ``state.processing.feedback_text`` /
        ``color_palette_config`` / ``selection_prompt``. Falls back to a
        minimal error message if the LLM call fails.

        If the raw user message contains ``#bypass_feedback``, skip the
        LLM call entirely and write the canned response directly to
        ``state.output.response``. The conditional edge out of this node
        then short-circuits to END (see ``route_after_feedback``).
        """
        logger().logp(DEBUG, "[NODE] feedback_node entered")
        processing = state.processing or {}
        inp = state.input or {}

        if "#bypass_feedback" in (inp.get("raw_user_input", "") or ""):
            logger().logp(INFO, "[NODE] feedback bypassed via #bypass_feedback shortcut")
            state.processing["feedback_text"] = "Feedback bypassed as per user request."
            state.processing["color_palette_config"] = None
            state.processing["selection_prompt"] = None
            return state

        user_id = inp.get("user_id")
        list_steps = list(processing.get("list_steps", []) or [])
        feedback_material = dict(processing.get("feedback_material", {}) or {})
        # Final-state tag update — by the time feedback runs, every step the
        # graph took is in list_steps. Last write wins, so this is the tag
        # set that shows up on the finalized trace in Langfuse.
        tag_current_trace(["request"] + list_steps)
        owner_id = inp.get("owner_id")
        room_id = inp.get("room_id")
        workspace = ws_path(owner_id, room_id)

        if not feedback_material:
            logger().logp(WARNING, "⚠️ No logs found in the state.")
            return state

        if "user_question" in list_steps:
            last_summary = read_metadata(owner_id, room_id, "last_viz_summary").get(
                "last_viz_summary"
            )
            if last_summary:
                feedback_material["last_viz_summary"] = last_summary

        ai_tone = await self.db.get_user_tone(user_id)

        messages = inp.get("message_history", []) or []
        last_exchange = format_message_history(messages[-3:]) if messages else ""

        cg_path = workspace / "choregraph.xml"
        if os.path.isfile(cg_path):
            spec = ChoregraphSpecParser.parse(cg_path)
            datasets_ids = [str(item.id) for item in spec.get_visible()]
            metadata = Metadata(workspace)
            data_stats = "\n".join(
                [f"{metadata.read_from_cache([id]).format('markdown')}" for id in datasets_ids]
            )
        else:
            data_stats = ""

        logger().logp(
            DEBUG,
            f"VIZ SUMMARY IN FEEDBACK NODE: {feedback_material.get('viz_summary', 'No summary found')}",
        )
        chat_template, variables = FeedbackMessage().build(
            list_steps=list_steps,
            personality_tone=ai_tone,
            feedback_material=feedback_material,
            data_stats=data_stats,
            last_exchange=last_exchange,
        )

        try:
            llm_cfg, node_cfg = get_call_config("feedback", config)
            response = await self.llm_manager.ainvoke(
                chat_template=chat_template,
                variables=variables,
                llm_config=llm_cfg,
                response_schema=FeedbackStructure,
                cost_label="Feedback Node",
                max_tokens=2000,
                **node_cfg,
            )

            if response is None:
                raise ValueError("LLM returned None after all retries")

            state.processing["feedback_text"] = clean_raw_feedback_output(response.feedback_text)
            state.processing["color_palette_config"] = response.color_palette_config
            state.processing["selection_prompt"] = response.selection_prompt
            return state

        except Exception as e:
            logger().logp(
                ERROR,
                f"❌ Error during LLM invocation in feedback node: {e}. "
                "Fallback responses will be sent to the user.",
            )
            if set(feedback_material.keys()) == {"question_answer", "user_question"}:
                state.processing["feedback_text"] = feedback_material.get("question_answer", "")
                state.processing["color_palette_config"] = None
                state.processing["selection_prompt"] = None
                return state

            feedback = "<em> We encountered an error while writing a report on your request. "
            if "upload" in feedback_material:
                feedback += "However, your file has been successfully processed. "
            if "ai_processing" in feedback_material:
                feedback += "Your visualization should still be accessible in the right-hand window. "
            if "question_answer" in feedback_material:
                feedback += (
                    f"Regarding your question, here is the answer: "
                    f"{feedback_material['question_answer']}. "
                )
            feedback += (
                "We apologize for the inconvenience and invite you to try again "
                "in a few moments.</em>"
            )
            logger().logp(ERROR, "Fallback feedback generated ; should not happen.")
            state.processing["feedback_text"] = feedback
            state.processing["color_palette_config"] = None
            state.processing["selection_prompt"] = None
            return state

    # ---- Terminal response formatter ------------------------------------

    def format_feedback(self, state):
        """Assemble the final HTTP response from ``feedback_node`` output.

        Reads ``state.processing.feedback_text`` (+ color palette /
        selection prompt / viz build state) and writes
        ``state.output.response = {text, suggestions, selection_prompt?}``.
        Called unconditionally after ``feedback_node`` — handles both the
        LLM-generated feedback and the ``#bypass_feedback`` canned text
        uniformly (both cases produce HTML-wrapped output).
        """
        logger().logp(DEBUG, "[NODE] format_feedback entered")
        processing = state.processing or {}
        feedback_material = processing.get("feedback_material", {}) or {}
        viz_build = processing.get("viz_build", {}) or {}

        raw_text = processing.get("feedback_text", "") or ""
        feedback_text = convert_feedback_to_html(raw_text)

        suggestions: list[dict] = []

        color_palette_config = processing.get("color_palette_config")
        if feedback_material.get("color_palette_request"):
            if color_palette_config:
                config_dict = (
                    color_palette_config.model_dump()
                    if hasattr(color_palette_config, "model_dump")
                    else color_palette_config
                )
                button_text = config_dict.get("button_text", "🎨 Customize colors")
                suggestions.append(
                    {
                        "text": button_text,
                        "type": "color_palette",
                        "config": {
                            "name": config_dict.get("name", "custom_palette"),
                            "type": config_dict.get("type", "SEQUENTIAL"),
                            "breaks": config_dict.get("breaks", []),
                        },
                    }
                )
                logger().logp(
                    INFO,
                    f"Injected color_palette suggestion with LLM-generated config: {config_dict}",
                )
            else:
                suggestions.append(
                    {
                        "text": "Customize colors",
                        "type": "color_palette",
                        "config": {
                            "name": "custom_palette",
                            "type": "SEQUENTIAL",
                            "breaks": [],
                        },
                    }
                )
                logger().logp(
                    WARNING,
                    "Color palette request but no LLM-generated config, using fallback",
                )

        viz_file = viz_build.get("viz_file") if viz_build.get("status") == "ok" else None
        if viz_file:
            viz_filename = sanitize_filename(pathlib.Path(viz_file).name)
            json_str = json.dumps({"file": viz_filename})
            config = html.escape(json_str)
            thumb_name = pathlib.Path(viz_filename).stem + ".png"
            room_token = state.input.get("room_token", "")
            thumb_url = (
                f"/server/rooms/{html.escape(room_token)}"
                f"/artifacts/{html.escape(thumb_name)}"
            )
            thumb_html = (
            f'<button class="viz-thumbnail-btn" data-viz-config="{config}" '
            f"""onclick="window.dispatchEvent(new CustomEvent('loadVizFile', """
            f"""{{detail: JSON.parse(this.dataset.vizConfig || '{{}}')}}));">"""
            f'<img src="{thumb_url}" loading="lazy" decoding="async" '
            f'alt="" class="viz-thumbnail" />'
            f'</button>'
            )
            # Replace placeholder inline if the LLM included it; otherwise fallback to append
            replaced, n = _VIZ_PLACEHOLDER_RE.subn(thumb_html, feedback_text, count=1)
            if n:
                feedback_text = replaced
            else:
                feedback_text += thumb_html
            feedback_text += (
                f'<div class="history-anchor">'
                f'<button class="history-show-viz" data-tooltip="Show visualization" '
                f'aria-label="Show visualization" '
                f'data-viz-config="{config}" '
                f"""onclick="window.dispatchEvent(new CustomEvent('loadVizFile', """
                f"""{{detail: JSON.parse(this.dataset.vizConfig || '{{}}')}}));">"""
                f'<img src="/icons/viz.svg" alt="" aria-hidden="true" '
                f'style="height: 1.2em; width: 1.2em; vertical-align: middle;" />'
                f'</button>'
                f'<button class="history-export-dashboard" data-tooltip="Export to dashboard" '
                f'aria-label="Export to dashboard" '
                f"""onclick="window.dispatchEvent(new CustomEvent('openExportModal'));">"""
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
                f'aria-hidden="true" '
                f'style="height: 1.2em; width: 1.2em; vertical-align: middle; fill: white; opacity: 0.8;">'
                f'<path d="M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z"/>'
                f'</svg>'
                f'</button>'
                f'</div>'
            )

        feedback_text = _VIZ_PLACEHOLDER_RE.sub("", feedback_text)

        response: dict[str, Any] = {"text": feedback_text, "suggestions": suggestions}

        selection_prompt = processing.get("selection_prompt")
        if selection_prompt:
            selection_prompt_data = (
                selection_prompt.model_dump()
                if hasattr(selection_prompt, "model_dump")
                else selection_prompt
            )
            response["selection_prompt"] = selection_prompt_data

        state.output["response"] = response
        return state

# ---------------------------------------------------------------------------
# Conditional routers
# ---------------------------------------------------------------------------


def route_to_asp(state) -> str:
    """Decide between ASP solving and direct feedback.

    Short-circuits to the feedback node when the XML produced upstream is
    empty (question-only turns, shortcut with no xml, etc.).
    """
    xml_output = ((state.processing or {}).get("xml_output") or "").strip()
    if not xml_output:
        return "feedback_node"
    return "asp_solving_node"


def route_to_viz(state) -> str:
    """After ASP, decide whether to render (web), end (SDK), or skip to feedback.

    - ASP failed / timed out → ``feedback_node`` (feedback reports the error).
    - ASP succeeded AND ``is_api=True`` → ``__end__``. The SDK client
      reads ``specifications.xml`` from the session workspace itself; the
      server neither renders a viz nor generates HTML feedback.
    - ASP succeeded AND web → ``viz_building_node``.
    """
    asp = (state.processing or {}).get("asp", {}) or {}
    if not asp.get("success"):
        return "feedback_node"
    if (state.input or {}).get("is_api"):
        return "__end__"
    return "viz_building_node"
