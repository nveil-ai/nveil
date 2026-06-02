# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""UserRequest workflow — unified LangGraph state machine.

This module defines the graph topology (nodes, edges, conditional routing).
Node implementations live in:

* :mod:`workflow_request_nodes`  — LLM calls + choregraph trigger
* :mod:`workflow_request_output` — shortcut expansion
* :mod:`workflow_postprocess_nodes` — ASP / viz_build / feedback / HTML
"""

from langgraph.graph import END, StateGraph
from langgraph.types import interrupt
from logger import DEBUG, ERROR, INFO, WARNING, logger
from shared.workspace import read_metadata, workspace_path as ws_path

from lxml import etree

from .workflow import Workflow, tag_current_trace
from .workflow_postprocess_nodes import (
    PostprocessNodesMixin,
    route_to_asp,
    route_to_viz,
)
from .workflow_request_nodes import RequestNodesMixin
from .workflow_request_output import OutputNodesMixin
from .workflow_state import WorkflowState
from .workflow_utils import combine_inputs


# One unified budget for every *automatic* retry cycle through
# planning_transformation_node, whether triggered by XSD validation
# failure or by a failed web choregraph run. Counts LLM calls, not
# cycle-back attempts — see ``planning_transformation_node`` for where
# the counter is incremented. Clarification retries have their own
# (human-driven) limit in ``consecutive_clarifications``.
MAX_PLANNING_RETRIES = 3


def route_after_choregraph(state) -> list[str] | str:
    """Fan-out or cycle-back after ``trigger_choregraph_run_node``.

    Three outcomes:

    - SDK path, or web path after a successful choregraph run
      (``choregraph_error`` not set) → fan out to the viz subgraph and,
      if requested, the exclusion branch.
    - Web path, choregraph failed with planning budget remaining →
      cycle back to ``planning_transformation_node`` for a fresh LLM
      call (never retry the same XML). Planning consumes
      ``choregraph_error`` and increments ``planning_retries`` on entry.
    - Web path, planning budget exhausted → land on ``feedback_node``
      with the error already recorded in ``feedback_material``.
    """
    processing = state.processing or {}
    if "choregraph_error" not in processing:
        if processing.get("need_exclusion_processing", False):
            return ["viz_processing_branch", "exclusion_processing"]
        return "viz_processing_branch"
    if processing.get("planning_retries", 0) < MAX_PLANNING_RETRIES:
        return "planning_transformation_node"
    return "feedback_node"


class UserRequest(RequestNodesMixin, OutputNodesMixin, PostprocessNodesMixin, Workflow):
    """LangGraph workflow for processing a single user message.

    Standard web flow::

        initialize_processing_state
          └─► entry_classif_message_type          [LLM + choregraph probe]
                  ├─► (color_palette / pure question / no_data) feedback_node
                  └─► planning_transformation_node              [LLM + XSD retry]
                         ▼
                  transformation_clarification_gate              [interrupt]
                         ▼
                  trigger_choregraph_run_node         [web: HTTP, SDK: interrupt]
                         ├─► (success)  fan out to viz + optional exclusion
                         │                └─► asp_solving_node (defer=True)
                         │                          ├─► (web ok)  viz_building_node ─► feedback_node
                         │                          ├─► (is_api + ok) END
                         │                          └─► (fail/skip)    feedback_node
                         ├─► (retry)    planning_transformation_node
                         └─► (max)      feedback_node

        feedback_node ─► format_feedback ─► END
    """

    trace_name = "user-request"
    trace_tags = ("request",)

    def compile(self):
        return self.create_main_graph()

    # ------------------------------------------------------------------
    # Helper nodes
    # ------------------------------------------------------------------

    def initialize_processing_state(self, state):
        """Seed ``state.processing`` from the request payload.

        Also primes ``feedback_material`` with everything already known
        at entry (language, user message, persistent additional info,
        upload log when applicable) so downstream nodes can append
        instead of assembling it from scratch later.
        """
        logger().logp(DEBUG, "[NODE] initialize_processing_state entered")
        if state.processing:
            logger().logp(DEBUG, f"Init node: residual processing keys = {list(state.processing.keys())}")

        workspace_path = ws_path(state.input["owner_id"], state.input["room_id"])
        viz_xml_path = workspace_path / "specifications.xml"
        previous_viz_xml = ""
        try:
            if viz_xml_path.exists():
                with open(viz_xml_path, "r", encoding="utf-8") as f:
                    previous_viz_xml = f.read()
                logger().logp(INFO, f"Loaded previous visualization XML from {viz_xml_path}")
        except Exception as e:
            logger().logp(ERROR, f"Error reading previous visualization XML: {e}")

        _lang_map = {"en": "english", "fr": "french", "de": "german", "es": "spanish", "it": "italian", "pt": "portuguese"}
        _lang_code = (state.input.get("user_language") or "en").lower().split("-")[0].split("_")[0]
        language = _lang_map.get(_lang_code, _lang_code)

        raw_user_input = state.input.get("raw_user_input", "") or ""
        user_request = raw_user_input.replace("#bypass_feedback", "").strip()

        persistent_info = state.input.get("additional_info", {}) or {}

        feedback_material = {
            "language": language,
            "user_last_message": raw_user_input,
        }
        if persistent_info:
            # Feedback prompt expects a pre-combined string, not a raw dict.
            feedback_material["persistent_additional_information"] = combine_inputs(persistent_info)

        list_steps: list[str] = []
        if state.input.get("is_an_upload_message"):
            list_steps.append("upload")
            try:
                meta = read_metadata(state.input["owner_id"], state.input["room_id"])
                log_info = (meta or {}).get("log_info") or ""
            except Exception as e:
                logger().logp(DEBUG, f"Metadata read failed: {e}")
                log_info = ""
            feedback_material["upload"] = "Your file has been uploaded successfully." + log_info

        state.processing = {
            "current_language": language,
            "user_request": user_request,
            "message_history": state.input.get("message_history", []),
            "previous_viz_xml": previous_viz_xml,
            "persistent_additional_information": persistent_info,
            "processing_error_feedback": [],
            "dynamic_asp_facts": [],
            "user_question": None,
            "xml_output": "",
            "number_of_retries": 0,
            "additional_information": [],
            "transformation_xml": "",
            "transformation_comments": "",
            "transformation_failed": False,
            "workspace_path": workspace_path,
            "consecutive_clarifications": 0,
            "color_palette_request": False,
            "list_steps": list_steps,
            "feedback_material": feedback_material,
        }
        # Tag the trace early with any step already decided at init (currently
        # `upload` for upload-only shortcuts that never go through classification).
        tag_current_trace(["request"] + list_steps)
        return state

    def shortcut_router(self, state):
        """Dispatch between shortcut, upload-only, and standard flow."""
        if state.input.get("raw_user_input", "").startswith("#nveil#"):
            return "expand_shortcut_node"
        if state.input.get("is_an_upload_message", False):
            return "feedback_node"
        return "entry_classif_message_type"

    def viz_subgraph_entry(self, state):
        """Entry gate for the viz subgraph; enables conditional check."""
        logger().logp(DEBUG, "[NODE] viz_subgraph_entry entered")
        return state

    def finalize_viz_step(self, state):
        """Finalize the viz subgraph step — merge validation errors into feedback_material."""
        logger().logp(DEBUG, "[NODE] finalize_viz_step entered")
        err = state.processing.get("processing_error_feedback")
        if err:
            logger().logp(WARNING, f"Viz subgraph completed with errors: {err}")
            feedback_material = dict(state.processing.get("feedback_material", {}) or {})
            feedback_material["ai_processing"] = err if isinstance(err, str) else "\n- ".join(err)
            state.processing["feedback_material"] = feedback_material
        from ..turn_metrics import get_turn_metrics
        tm = get_turn_metrics()
        if tm:
            tm.record_retries("XML Generation", state.processing.get("number_of_retries", 0))
        return state

    def increment_retrying_index(self, state):
        logger().logp(DEBUG, "[NODE] increment_retrying_index entered")
        state.processing["number_of_retries"] = state.processing.get("number_of_retries", 0) + 1
        return state

    # ------------------------------------------------------------------
    # Interrupt gates
    # ------------------------------------------------------------------

    def transformation_clarification_gate(self, state):
        """Pause the graph when planning asked for clarification.

        API calls (``is_api=True``) never interrupt — single-shot generation.
        Re-entry on resume is a no-op on the pause side (``interrupt()``
        returns the resume value instead of pausing a second time).
        """
        logger().logp(DEBUG, "[NODE] transformation_clarification_gate entered")
        pending = state.processing.get("pending_clarification")
        if not pending:
            state.processing["consecutive_clarifications"] = 0
            return state

        if state.input.get("is_api"):
            state.processing["pending_clarification"] = None
            return state

        clarif_count = state.processing.get("consecutive_clarifications", 0)
        if clarif_count >= 2:
            state.processing["pending_clarification"] = None
            return state

        user_response = interrupt(pending)
        state.processing["user_clarification"] = user_response
        state.processing["pending_clarification"] = None
        return state

    # ------------------------------------------------------------------
    # Routers (string-returning)
    # ------------------------------------------------------------------

    def is_there_a_viz_request(self, state):
        return str("visualization_request" in state.processing.get("list_steps", []))

    def should_retry(self, state):
        max_retries = 3
        has_errors = bool(state.processing.get("processing_error_feedback"))
        retries = state.processing.get("number_of_retries", 0)
        if not has_errors:
            return "NO_RETRY"
        if retries < max_retries:
            logger().logp(WARNING, f"XML invalid, retrying (attempt {retries+1})...")
            return "RETRY"
        logger().logp(ERROR, f"Max retries ({max_retries}) reached. Aborting.")
        return "NO_RETRY"

    def need_intent_classification(self, state):
        if state.processing.get("processing_error_feedback"):
            return "False"
        try:
            xml_output = state.processing.get("xml_output", "")
            marks_element = etree.fromstring(xml_output.encode("utf-8") if isinstance(xml_output, str) else xml_output).find(".//marks")
            if marks_element is not None:
                names = [child.tag for child in marks_element]
                if "mark" in names:
                    return "True"
        except etree.XMLSyntaxError:
            pass
        return "False"

    def route_after_clarification_gate(self, state):
        """Decide what happens after the clarification gate.

        Priority order:
        - User answered a clarification (``user_clarification`` set) → loop back
          to planning. Clarification retries are human-driven and bounded by
          ``consecutive_clarifications``, not the LLM budget.
        - Planning hit an XSD error on the last attempt AND the budget allows
          → cycle back to planning for another LLM attempt. ``planning_retries``
          is bumped on re-entry.
        - Planning failed hard (``transformation_failed`` with no retryable
          signal, or budget exhausted) → land on feedback_node.
        - Otherwise → proceed to choregraph trigger.
        """
        processing = state.processing or {}
        if processing.get("user_clarification"):
            return "retry_transformation"
        if processing.get("xsd_error") and processing.get("planning_retries", 0) < MAX_PLANNING_RETRIES:
            return "retry_transformation"
        if processing.get("transformation_failed", False) or processing.get("xsd_error"):
            logger().logp(WARNING, "Transformation failed or budget exhausted. Stopping.")
            return "feedback_node"
        return "trigger_choregraph_run_node"

    def router_after_classification(self, state):
        """Dispatch after entry_classif_message_type.

        Direct-to-feedback cases:
        - color_palette_request
        - no_data_guidance (no choregraph.xml / no inputs)
        - pure question / info (no transformation AND no viz request)

        Otherwise → ``planning_transformation_node``.
        """
        processing = state.processing or {}
        if processing.get("color_palette_request"):
            return "feedback_node"
        if processing.get("no_data_guidance"):
            return "feedback_node"
        has_viz_request = bool((processing.get("user_request") or "").strip())
        need_transformation = processing.get("need_transformation", False)
        if need_transformation or has_viz_request:
            return "planning_transformation_node"
        return "feedback_node"

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _create_viz_subgraph(self):
        """Viz subgraph: XML generation + validation retry loop."""
        subgraph = StateGraph(WorkflowState)

        subgraph.add_node("viz_subgraph_entry", self.viz_subgraph_entry)
        subgraph.add_node("finalize_viz_step", self.finalize_viz_step)
        subgraph.add_node("xml_generation", self.xml_generation)
        subgraph.add_node("xml_validator", self.xml_validator)
        subgraph.add_node("increment_retrying_index", self.increment_retrying_index)
        subgraph.add_node("classify_user_intention", self.classify_user_intention)

        subgraph.set_entry_point("viz_subgraph_entry")
        subgraph.add_conditional_edges(
            "viz_subgraph_entry",
            self.is_there_a_viz_request,
            {"False": END, "True": "xml_generation"},
        )

        subgraph.add_edge("xml_generation", "xml_validator")

        subgraph.add_conditional_edges(
            "xml_validator",
            self.should_retry,
            {"NO_RETRY": "finalize_viz_step", "RETRY": "increment_retrying_index"},
        )
        subgraph.add_edge("increment_retrying_index", "xml_generation")

        subgraph.add_conditional_edges(
            "finalize_viz_step",
            self.need_intent_classification,
            {"True": "classify_user_intention", "False": END},
        )
        subgraph.add_edge("classify_user_intention", END)

        return subgraph.compile(checkpointer=False)

    def create_main_graph(self):
        """Create the main state graph."""
        graph = StateGraph(WorkflowState)

        # --- Nodes ---
        graph.add_node("initialize_processing_state", self.initialize_processing_state)
        graph.add_node("entry_classif_message_type", self.entry_classif_message_type)
        graph.add_node("expand_shortcut_node", self.expand_shortcut_node)

        graph.add_node("exclusion_processing", self.exclusion_processing)
        viz_subgraph_app = self._create_viz_subgraph()
        graph.add_node("viz_processing_branch", viz_subgraph_app)

        graph.add_node("planning_transformation_node", self.planning_transformation_node)
        graph.add_node("transformation_clarification_gate", self.transformation_clarification_gate)
        graph.add_node("trigger_choregraph_run_node", self.trigger_choregraph_run_node)

        # `defer=True` makes asp_solving_node wait for every scheduled
        # predecessor (viz_processing_branch + optional exclusion_processing)
        # before running — replaces the old merge_parallel_results barrier.
        graph.add_node("asp_solving_node", self.asp_solving_node, defer=True)
        graph.add_node("viz_building_node", self.viz_building_node)
        graph.add_node("feedback_node", self.feedback_node)
        graph.add_node("format_feedback", self.format_feedback)

        # --- Entry ---
        graph.set_entry_point("initialize_processing_state")
        graph.add_conditional_edges(
            "initialize_processing_state",
            self.shortcut_router,
            {
                "entry_classif_message_type": "entry_classif_message_type",
                "expand_shortcut_node": "expand_shortcut_node",
                "feedback_node": "feedback_node",
            },
        )

        # --- Shortcut path (#nveil#*) goes through ASP + (web) viz_build ---
        graph.add_conditional_edges(
            "expand_shortcut_node",
            route_to_asp,
            {"asp_solving_node": "asp_solving_node", "feedback_node": "feedback_node"},
        )

        # --- Classification → transformation or direct feedback ---
        graph.add_conditional_edges(
            "entry_classif_message_type",
            self.router_after_classification,
            {
                "planning_transformation_node": "planning_transformation_node",
                "feedback_node": "feedback_node",
            },
        )

        # --- Planning → clarification gate → choregraph trigger ---
        graph.add_edge("planning_transformation_node", "transformation_clarification_gate")
        graph.add_conditional_edges(
            "transformation_clarification_gate",
            self.route_after_clarification_gate,
            {
                "retry_transformation": "planning_transformation_node",
                "trigger_choregraph_run_node": "trigger_choregraph_run_node",
                "feedback_node": "feedback_node",
            },
        )

        # --- Choregraph trigger: fan out on success, cycle back on retryable failure ---
        graph.add_conditional_edges(
            "trigger_choregraph_run_node",
            route_after_choregraph,
            [
                "viz_processing_branch",
                "exclusion_processing",
                "planning_transformation_node",
                "feedback_node",
            ],
        )

        # --- Parallel branches converge on asp_solving_node (defer=True) ---
        graph.add_edge("exclusion_processing", "asp_solving_node")
        graph.add_edge("viz_processing_branch", "asp_solving_node")

        # --- ASP → viz_build (web) / END (SDK) / feedback (skip or fail) ---
        graph.add_conditional_edges(
            "asp_solving_node",
            route_to_viz,
            {
                "viz_building_node": "viz_building_node",
                "feedback_node": "feedback_node",
                "__end__": END,
            },
        )

        # --- Viz build always funnels into feedback_node for HTML assembly ---
        graph.add_edge("viz_building_node", "feedback_node")

        # --- Feedback → format_feedback (unconditional) → END ---
        graph.add_edge("feedback_node", "format_feedback")
        graph.add_edge("format_feedback", END)

        return graph.compile(checkpointer=self.checkpointer)
