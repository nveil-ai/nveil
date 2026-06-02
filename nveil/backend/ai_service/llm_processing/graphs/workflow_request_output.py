# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Shortcut expansion node for the UserRequest graph.

Historically this module held the ``prepare_*_processing_state`` family
of nodes — thin rewiring nodes that existed only to hand state off
between the old ``main_graph`` and the old ``feedback_graph``. Since
the two graphs merged, ``feedback_material`` is now built along the way
by the nodes that actually produce each piece, and those rewiring nodes
are gone.

What remains is :class:`OutputNodesMixin.expand_shortcut_node`: the
functional handler for the ``#nveil#*`` shortcuts (test harnesses and
"replay previous visualisation" flows). It parses the shortcut form out
of ``state.input["raw_user_input"]`` and seeds ``xml_output`` and
``feedback_material`` so the downstream ASP / viz / feedback chain runs
identically to a normal turn.
"""

import re

from viz_file_utils.utils.viz_spec_validator import XMLSpecProcessor
from logger import DEBUG, ERROR, INFO, logger

from ..config import XSD_FILEPATH


class OutputNodesMixin:
    """Mixin providing the shortcut-expansion node."""

    def expand_shortcut_node(self, state):
        """Expand a ``#nveil#*`` shortcut into graph-ready state.

        Four supported shortcuts:

        - ``#nveil#output_xml <xml>`` — validate the supplied VisuSpec XML
          and treat it as the LLM-generated XML for this turn.
        - ``#nveil#previous_xml`` — reuse ``specificationsBeforeAI.xml``
          from the workspace (the last pre-ASP spec).
        - ``#nveil#question_nveil <q>`` — inject a canned company question.
        - ``#nveil#question_other <q>`` — inject a canned generic question.

        Writes only the canonical keys: ``xml_output``,
        ``dynamic_asp_facts``, ``user_question``, ``feedback_material``,
        ``list_steps`` (no intermediate ``viz`` / ``info`` / ``question``
        indirection — consumers read from the canonical keys directly).
        """
        logger().logp(DEBUG, "[NODE] expand_shortcut_node entered")
        raw_input = state.input.get("raw_user_input", "") or ""
        feedback_material = dict(state.processing.get("feedback_material", {}) or {})

        if raw_input.startswith("#nveil#output_xml"):
            pattern = r"<datas>.*?</datas>"
            artificial_output = (
                raw_input.replace("#nveil#output_xml", "").strip()
                .replace("visuSpecAI", "visuSpec")
                .replace("visuSpec", "visuSpecAI")
            )
            artificial_output = re.sub(pattern, "", artificial_output, flags=re.DOTALL)
            spec_processor = XMLSpecProcessor(artificial_output, XSD_FILEPATH)
            is_valid, errors, artificial_output = spec_processor.validate_xml_string_with_xsd()
            if not is_valid:
                err_text = "The provided XML output is not valid. Please check the structure and try again.\nErrors:\n- " + "\n- ".join(errors)
                logger().logp(ERROR, err_text)
                artificial_output = ""
                feedback_material["ai_processing"] = err_text
            state.processing["xml_output"] = artificial_output
            state.processing["dynamic_asp_facts"] = []
            state.processing["list_steps"] = ["visualization_request"]
            state.processing["feedback_material"] = feedback_material
            return state

        if raw_input.startswith("#nveil#previous_xml"):
            logger().logp(DEBUG, "[SHORTCUT] Using previous XML output generated...")
            viz_xml_path = state.processing["workspace_path"] / "specificationsBeforeAI.xml"
            previous_viz_xml = ""
            try:
                if viz_xml_path.exists():
                    with open(viz_xml_path, "r", encoding="utf-8") as f:
                        previous_viz_xml = f.read()
                        pattern = r"<datas>.*?</datas>"
                        previous_viz_xml = re.sub(pattern, "", previous_viz_xml, flags=re.DOTALL)
                    logger().logp(INFO, f"Loaded previous visualization XML from {viz_xml_path}")
                else:
                    logger().logp(ERROR, f"No previous visualization XML found at {viz_xml_path}")
            except Exception as e:
                logger().logp(ERROR, f"Error reading previous visualization XML: {e}")
            state.processing["xml_output"] = previous_viz_xml
            state.processing["dynamic_asp_facts"] = []
            state.processing["list_steps"] = ["visualization_request"]
            state.processing["feedback_material"] = feedback_material
            return state

        if raw_input.startswith("#nveil#question_nveil"):
            artificial_question = raw_input.replace("#nveil#question_nveil", "").strip()
            state.processing["xml_output"] = ""
            state.processing["dynamic_asp_facts"] = []
            state.processing["user_question"] = {"company_related": artificial_question, "other": None}
            feedback_material["user_question"] = state.processing["user_question"]
            state.processing["feedback_material"] = feedback_material
            state.processing["list_steps"] = ["user_question"]
            return state

        if raw_input.startswith("#nveil#question_other"):
            artificial_question = raw_input.replace("#nveil#question_other", "").strip()
            state.processing["xml_output"] = ""
            state.processing["dynamic_asp_facts"] = []
            state.processing["user_question"] = {"company_related": None, "other": artificial_question}
            feedback_material["user_question"] = state.processing["user_question"]
            state.processing["feedback_material"] = feedback_material
            state.processing["list_steps"] = ["user_question"]
            return state

        return state
