# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""LLM-calling node implementations for the UserRequest graph.

This module contains the RequestNodesMixin class providing all nodes that
invoke the LLM (classification, XML generation, exclusion, keyword
classification, transformation).  Mixed into UserRequest via multiple
inheritance.

All LLM-calling nodes are ``async def`` so that LangGraph executes
parallel branches via ``asyncio.gather`` instead of a thread pool.
"""

import copy
import re
from typing import List

from viz_file_utils.utils.viz_spec_validator import XMLSpecProcessor
from logger import DEBUG, ERROR, INFO, WARNING, logger
from lxml import etree
from pydantic import BaseModel, ConfigDict

from choregraph import Choregraph
from choregraph.metadata import Metadata
from choregraph.parser import ChoregraphSpecParser

from langchain_core.messages import HumanMessage
from langgraph.types import interrupt

from ..config import SERVER_HOST, SERVER_PORT, XSD_FILEPATH
from ..debug_errors import log_visuspec_error, log_choregraph_error
from ..graphs.workflow_request_classify import (
    ListLLMResponseClassification, compute_adaptative_threshold,
    compute_mark_scores)
from ..graphs.workflow_request_exclusion import ExclusionFactBuilder
from ..node_config import get_call_config
from ..prompt import (EntrypointClassification, ExclusionProcessing,
                      KeywordClassification, PlanningTransformationNormal,
                      PlanningTransformationFallback, XMLGeneration)
from .workflow import tag_current_trace
from .workflow_postprocess_nodes import SelectionPromptModel
from .workflow_utils import (clean_message_content,
                             combine_inputs, merge_additional_info,
                             format_message_history, remove_empty_channels)
from ..turn_metrics import get_turn_metrics


# ---------- Pydantic response schemas ----------
#
# Every schema below is OpenAI-strict-compatible:
# - `extra="forbid"`            → adds `additionalProperties: false`
# - no field defaults           → all properties land in `required`
# - nullables use `X | None`    → the LLM signals "absent" via explicit `null`
#
# Enforced by test_workflow_request_output.test_all_response_schemas_are_strict.

class AdditionalInfoType(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_related: str | None
    room_related: str | None

class QuestionType(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_related: str | None
    other: str | None

class MessageTypeClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    visualization_request: str | None
    additional_info: AdditionalInfoType | None
    questions: QuestionType | None
    exclusion_request: bool
    transformation_request: bool
    color_palette_request: bool
    language: str | None

class Exclusion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selector: str
    value: str | None
    scope: str | None
    long_term: bool

class Exclusions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exclusions: List[Exclusion]

class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    visualization_plan: str | None
    transformation_plan: str | None

class TransformationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transformation_xml: str | None
    comments: str | None
    plan: Plan | None
    transformation_failed: bool
    early_exit: bool
    feedback_text: str | None
    selection_prompt: SelectionPromptModel | None

class FallbackTransformationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transformation_xml: str



# ---------- Mixin ----------

class RequestNodesMixin:
    """Mixin providing all LLM-calling graph nodes for UserRequest.

    All nodes that perform network I/O (LLM calls, HTTP requests) are
    ``async def`` so that LangGraph parallel branches run via
    ``asyncio.gather`` rather than a thread pool.
    """

    async def _post_stage(self, room_token: str, stage: str, label: str):
        """Fire-and-forget stage notification via the shared httpx client."""
        if not self.http_client or not room_token:
            return
        try:
            await self.http_client.post(
                f"https://{SERVER_HOST}:{SERVER_PORT}/server/stage",
                json={"room_token": room_token, "stage": stage, "label": label},
                timeout=3.0,
            )
        except Exception:
            pass  # Stage updates are non-critical

    async def entry_classif_message_type(self, state, config):
        """Classify the type of user message and probe data availability.

        Also inlines what used to be the ``check_data_availability_node``
        (cheap filesystem probe: if ``choregraph.xml`` is missing or has
        no inputs, set ``no_data_guidance=True`` so the router can short-
        circuit to ``feedback_node``). Every piece of information this
        node produces is mirrored into ``state.processing.feedback_material``
        so downstream nodes don't need a re-assembly step.
        """
        logger().logp(DEBUG, "[NODE] entry_classif_message_type entered")

        # --- Data-availability probe (formerly lambda_node_post_upload_router) ---
        choregraph_xml_path = state.processing["workspace_path"] / "choregraph.xml"
        if not choregraph_xml_path.exists():
            state.processing["no_data_guidance"] = True
        else:
            try:
                spec = ChoregraphSpecParser.parse(choregraph_xml_path)
                inputs_ids = spec.select_by_tag('input').get_attribute('id')
                if not inputs_ids:
                    state.processing["no_data_guidance"] = True
            except Exception as e:
                logger().logp(WARNING, f"choregraph.xml parse failed during data probe: {e}")
                state.processing["no_data_guidance"] = True

        feedback_material = dict(state.processing.get("feedback_material", {}) or {})
        list_steps: list[str] = list(state.processing.get("list_steps", []) or [])
        if state.processing.get("no_data_guidance") and "no_data_guidance" not in list_steps:
            list_steps.append("no_data_guidance")

        # --- LLM classification ---
        state.processing['list_steps'] = list_steps
        if not state.processing["user_request"] or state.processing["user_request"].strip() == "":
            logger().logp(WARNING, "No user message found for classification.")
            state.processing["user_request"] = ""
            state.processing["feedback_material"] = feedback_material
            return state
        logger().logp(INFO, f"User message: {state.processing['user_request']}")
        latest_ai_response = format_message_history(state.processing.get("message_history", []), max_tokens=200)
        chat_template, variables =EntrypointClassification().build(
            message=state.processing["user_request"],
            latest_ai_response=clean_message_content(latest_ai_response),
        )

        llm_cfg, node_cfg = get_call_config("entry_classification", config)
        response = await self.llm_manager.ainvoke(
            chat_template=chat_template,
            variables=variables,
            llm_config=llm_cfg,
            response_schema=MessageTypeClassification,
            cost_label='Entry Point Message Type Classification',
            **node_cfg,
        )

        state.processing["user_request"] = ""
        if response is None:
            logger().logp(ERROR, "No structured response received from LLM for message classification.")
            state.processing["feedback_material"] = feedback_material
            return state

        logger().logp(INFO, f"Response of the message type classification: {response}")
        state.processing['need_exclusion_processing'] = response.exclusion_request
        state.processing['need_transformation'] = response.transformation_request
        # A message prefixed with #custom_palette carries an already-injected palette;
        # skip the palette-creation branch regardless of what the LLM classified.
        has_injected_palette = "#custom_palette" in state.processing.get("user_request", "")
        state.processing['color_palette_request'] = response.color_palette_request and not has_injected_palette
        language = response.language or state.processing.get("current_language", "english")
        state.processing['current_language'] = language
        feedback_material["language"] = language

        if state.processing['color_palette_request']:
            list_steps.append('color_palette_request')
            feedback_material["color_palette_request"] = True

        if response.visualization_request is not None and response.visualization_request.strip() != "":
            list_steps.append('visualization_request')
            state.processing["user_request"] = response.visualization_request.strip()
        else:
            state.processing["user_request"] = ""

        if response.additional_info is not None:
            list_steps.append('additional_info')
            additional_info_dict = response.additional_info.model_dump()
            state.processing["additional_information"] = additional_info_dict
            merged_persistent = merge_additional_info(
                state.processing["persistent_additional_information"], additional_info_dict
            )
            state.processing["persistent_additional_information"] = merged_persistent
            feedback_material["additional_information"] = combine_inputs(additional_info_dict)
            # Refresh the feedback-prompt view of persistent info with the post-merge dict.
            if merged_persistent:
                feedback_material["persistent_additional_information"] = combine_inputs(merged_persistent)

        if response.questions is not None:
            list_steps.append('user_question')
            q = response.questions.model_dump()
            state.processing["user_question"] = q
            feedback_material["user_question"] = q

        state.processing['list_steps'] = list(dict.fromkeys(list_steps))
        state.processing["feedback_material"] = feedback_material
        # Reflect the classified action types on the Langfuse trace.
        tag_current_trace(["request"] + state.processing['list_steps'])
        return state

    async def exclusion_processing(self, state, config):
        """Process exclusion requests into ASP facts."""
        logger().logp(DEBUG, "[NODE] exclusion_processing entered")

        spec = ChoregraphSpecParser.parse(state.processing["workspace_path"] / "choregraph.xml")
        inputs_ids = spec.select_by_tag('input').get_attribute('id')
        metadata = Metadata(state.processing["workspace_path"])
        data_stats = "\n".join([f"{metadata.read_from_cache(name).format('markdown')}" for name in inputs_ids])

        chat_template, variables =ExclusionProcessing().build(
            user_message=state.input["raw_user_input"],
            previous_viz_xml=state.processing.get("previous_viz_xml", ""),
            raw_data=data_stats,
        )
        llm_cfg, node_cfg = get_call_config("exclusion_processing", config)
        response = await self.llm_manager.ainvoke(
            chat_template=chat_template,
            variables=variables,
            llm_config=llm_cfg,
            response_schema=Exclusions,
            cost_label='Exclusion Processing Node',
            **node_cfg,
        )

        if response is None:
            logger().logp(ERROR, "No structured response received from LLM for exclusion processing.")
            return state

        logger().logp(INFO, f"Response of the exclusion processing: {response}")
        facts = []
        fact_builder = ExclusionFactBuilder()
        for exclusion in response.exclusions:
            selector = exclusion.selector or ""
            value = exclusion.value or ""
            scope = exclusion.scope or "*"
            built = fact_builder.build_asp_fact(selector, value, scope)
            for fact in built:
                if fact not in facts:
                    facts.append(fact)

        existing = state.processing.get("dynamic_asp_facts", [])
        state.processing["dynamic_asp_facts"] = existing + facts
        return state

    async def xml_generation(self, state, config):
        """Generate VisuSpec XML from user request and data statistics."""
        logger().logp(DEBUG, "[NODE] xml_generation entered")
        await self._post_stage(state.input["room_token"], "viz_xml_generation", "Visualization interpretation")
        try:
            if state.processing['persistent_additional_information'] and len(state.processing["persistent_additional_information"]) > 0:
                str_additional_info = combine_inputs(state.processing["persistent_additional_information"])
                user_request_formatted = """
Contextual information regarding the request:
___
{additional_info}
___
User request:
___
{user_request}
___
                """.format(
                    additional_info=str_additional_info,
                    user_request=state.processing["user_request"],
                )
            else:
                user_request_formatted = """
User request:
---
{user_request}
---
        """.format(
                    user_request=state.processing["user_request"]
                )

            if len(state.processing["processing_error_feedback"]) > 0:
                errors_str = state.processing["processing_error_feedback"]
                user_request_formatted += f"\nDuring your previous attempt... errors:\n- {errors_str}\n"
        except Exception as e:
            logger().logp(ERROR, f"Error while formatting user request: {e}")
            user_request_formatted = state.processing["user_request"]

        spec = ChoregraphSpecParser.parse(state.processing["workspace_path"] / "choregraph.xml")
        datasets_ids = [str(item.id) for item in spec.get_visible()]
        if not datasets_ids:
            logger().logp(WARNING, "No visible datasets found in choregraph.xml, all inputs will be considered in the visualization.")
            datasets_ids = [str(item.id) for item in spec.inputs]
        datasets_ids = [str(item.id) for item in spec.get_visible()]
        metadata = Metadata(state.processing["workspace_path"])

        plan = state.processing.get("plan", "")
        user_msg = state.processing['user_request'] + (' ' + plan if plan else '')
        data_stats = "\n".join([f"{metadata.read_from_cache([id]).format('markdown', user_message=user_msg)}" for id in datasets_ids])

        chat_template, variables =XMLGeneration().build(
            user_request=user_request_formatted,
            data_stats=data_stats,
            visualization_plan=state.processing.get("plan", ""),
        )

        llm_cfg, node_cfg = get_call_config("xml_generation", config)
        response = await self.llm_manager.ainvoke(
            chat_template=chat_template,
            variables=variables,
            llm_config=llm_cfg,
            response_schema=None,
            cache_name="xml_generation",
            cost_label='XML Generation Node',
            **node_cfg,
        )
        clean = re.sub(r"^```(?:xml)?\s*\n?", "", response.strip())
        clean = re.sub(r"\n?```\s*$", "", clean).strip()
        try:
            state.processing["xml_output"] = remove_empty_channels(clean)
        except Exception as e:
            logger().logp(WARNING, f"Failed removing empty channels from XML output: {e}. Using raw response.")
            state.processing["xml_output"] = clean
        logger().logp(DEBUG, f"XML output generated: {state.processing['xml_output']}")
        return state

    def xml_validator(self, state):
        """Validate XML output against the VisuSpec XSD schema.

        Kept synchronous — CPU-bound XML parsing runs in a thread pool
        when the graph executes via ``ainvoke``.
        """
        logger().logp(DEBUG, "[NODE] xml_validator entered")
        spec_processor = XMLSpecProcessor(state.processing["xml_output"], XSD_FILEPATH)
        state.processing["xml_output"] = spec_processor.xml_str
        state.processing['processing_error_feedback'] = []
        is_valid, errors, xml_output = spec_processor.validate_xml_string_with_xsd()
        if is_valid:
            state.processing["xml_output"] = xml_output
            state.processing["processing_error_feedback"] = ""
        else:
            logger().logp(WARNING, "XML output is not valid.")
            formatted_errors = "\n- ".join(errors)
            state.processing["processing_error_feedback"] = formatted_errors
            state.processing["xml_output"] = ""
            log_visuspec_error(
                errors,
                attempt=state.processing.get("number_of_retries"),
                room_id=state.input.get("room_id"),
            )
        return state

    async def classify_user_intention(self, state, config):
        """Classify user intent into mark type concepts (ASP facts)."""
        logger().logp(DEBUG, "[NODE] classify_user_intention entered")
        try:
            if state.processing["xml_output"].strip() is None:
                logger().logp(WARNING, "No XML output to classify user intention from.")
                state.processing["dynamic_asp_facts"] = []
                return state
            chat_template, variables =KeywordClassification().build(
                user_message=state.processing["user_request"],
                complementary_information=combine_inputs(state.processing["persistent_additional_information"]),
            )
            try:
                llm_cfg, node_cfg = get_call_config("keyword_classification", config)
                response = await self.llm_manager.ainvoke(
                    chat_template=chat_template,
                    variables=variables,
                    llm_config=llm_cfg,
                    response_schema=ListLLMResponseClassification,
                    cost_label='Keyword Classification',
                    **node_cfg,
                )
                classification = response.items
            except Exception as e:
                logger().logp(ERROR, f"Error during keyword classification: {e}")
                classification = []

            logger().logp(INFO, f"User intent classification: {classification}")
            LOWEST_CONFIDENCE_THRESHOLD = 0.5

            scores, _, count = compute_mark_scores(classification, with_best_stats=True)
            logger().logp(INFO, f"Computed mark scores from classification: {scores} ; COUNT = {count}")
            # Exclude 'text' from threshold computation — its high scores skew the threshold
            scores_without_text = {m: s for m, s in scores.items() if m.lower() != "text"}
            best_score = max(scores_without_text.values()) if len(scores_without_text) > 0 else 0
            if best_score < LOWEST_CONFIDENCE_THRESHOLD:
                logger().logp(WARNING, "No relevant marks found from user intent classification. Keeping the original XML output.")
                return state
            adaptative_threshold = compute_adaptative_threshold(
                best_score, LOWEST_CONFIDENCE_THRESHOLD, nb_attr_normalization=count
            )
            keywords_to_keep = [mark for mark, score in scores_without_text.items() if score >= adaptative_threshold]
            dynamic_facts = ["concept({})".format(k.lower()) for k in keywords_to_keep]
            # Always include concept(text) as a fallback
            if "concept(text)" not in dynamic_facts:
                dynamic_facts.append("concept(text)")
            logger().logp(INFO, f"Generated dynamic ASP facts for suggested marks: {dynamic_facts}")
            state.processing["dynamic_asp_facts"] = dynamic_facts
            return state
        except Exception as e:
            logger().logp(ERROR, f"Error during user intention classification: {e}")
            state.processing["dynamic_asp_facts"] = 'concept(text)'
            return state

    async def planning_transformation_node(self, state, config):
        """Generate Choregraph transformation XML — single LLM call per entry.

        Produces a valid ``choregraph.xml`` on disk and populates
        ``state.processing`` with ``transformation_xml``, ``plan``,
        ``transformation_comments`` (also mirrored into
        ``feedback_material``) and failure flags. The actual choregraph
        *execution* (HTTP POST or SDK interrupt) happens in the
        downstream ``trigger_choregraph_run_node``.

        **Single budget for retries.** One counter, ``planning_retries``,
        covers every automatic retry of this node (XSD validation failures
        AND failed choregraph runs), bounded by ``MAX_PLANNING_RETRIES``
        (set to 3 in :mod:`workflow_request`). Each LLM call through this
        node consumes one budget slot. Clarification retries are
        human-driven and bounded separately by ``consecutive_clarifications``.
        The internal for-loop retry that used to live here is gone — the
        graph cycle is now the single retry mechanism, which guarantees
        we never re-invoke choregraph on the same XML.

        On re-entry:
        - ``choregraph_error`` means a prior choregraph run failed at
          runtime → inject into the prompt, increment counter.
        - ``xsd_error`` means a prior LLM output didn't validate →
          inject into the prompt, increment counter.
        - ``user_clarification`` means the user answered an interrupt →
          inject into the prompt, do NOT count against the automatic budget.
        """
        logger().logp(DEBUG, "[NODE] planning_transformation entered")
        # Clean up stale clarification step from a previous interrupt-resume cycle
        if 'transformation_clarification' in state.processing.get('list_steps', []):
            state.processing['list_steps'].remove('transformation_clarification')
        state.processing['list_steps'].append('transformation_feedback')
        tag_current_trace(["request"] + state.processing['list_steps'])
        await self._post_stage(state.input["room_token"], "choregraph_xml_gen", "Transformation Research")
        xsd_schema_str = Choregraph().get_xsd()

        try:
            xsd_root = etree.XML(xsd_schema_str.encode('utf-8'))
            xml_schema = etree.XMLSchema(xsd_root)
        except Exception as e:
            logger().logp(ERROR, f"Invalid XSD Schema definition: {e}")
            raise e

        choregraph_xml_path = state.processing['workspace_path'] / "choregraph.xml"
        original_choregraph_content = ""  # Full XML with absolute paths (for reconciliation)
        choregraph_content = ""           # Stripped paths (for LLM prompt only)

        def _restore_inputs_visibility():
            """Reset choregraph.xml: set all inputs visible, remove pipeline nodes.

            Called when the LLM decides no transformation is needed so that
            xml_generation sees the original datasets via get_visible().
            """
            if not choregraph_xml_path.exists():
                return
            try:
                doc = etree.parse(str(choregraph_xml_path))
                root = doc.getroot()
                for inp in root.findall('.//inputs/input'):
                    inp.set('visibility', 'true')
                pipeline_elem = root.find('pipeline')
                if pipeline_elem is not None:
                    root.remove(pipeline_elem)
                doc.write(str(choregraph_xml_path), pretty_print=True, xml_declaration=True, encoding='utf-8')
                logger().logp(INFO, "Restored choregraph.xml: all inputs visible, pipeline cleared.")
            except Exception as e:
                logger().logp(WARNING, f"Failed to restore choregraph.xml input visibility: {e}")

        def _write_transformation_comments(comments: str) -> None:
            """Mirror transformation_comments into feedback_material."""
            state.processing["transformation_comments"] = comments or ""
            if comments:
                fm = dict(state.processing.get("feedback_material", {}) or {})
                fm["transformation_comments"] = comments
                state.processing["feedback_material"] = fm
        try:
            if choregraph_xml_path.exists():
                with open(choregraph_xml_path, "r", encoding="utf-8") as f:
                    original_choregraph_content = f.read()
                choregraph_content = original_choregraph_content
                try:
                    cg_doc = etree.fromstring(original_choregraph_content.encode("utf-8"))
                    for inp in cg_doc.findall(".//input"):
                        loc = inp.get("location")
                        if loc:
                            inp.set("location", loc.split("/")[-1])
                    choregraph_content = etree.tostring(cg_doc, pretty_print=True, xml_declaration=True, encoding="utf-8").decode("utf-8")
                except Exception as strip_err:
                    logger().logp(WARNING, f"Could not strip paths from choregraph.xml locations: {strip_err}")
            else:
                logger().logp(DEBUG, f"No choregraph.xml found at {choregraph_xml_path}")
        except Exception as e:
            logger().logp(ERROR, f"Error reading choregraph.xml: {e}")

        spec = ChoregraphSpecParser.parse(choregraph_xml_path)
        inputs_ids = spec.select_by_tag('input').get_attribute('id')
        metadata = Metadata(state.processing["workspace_path"])
        data_table = "\n".join([f"{metadata.read_from_cache([name]).format('markdown')}" for name in inputs_ids])
        # Build initial prompt variables — `user_request` may be extended below
        # with retry / clarification text before the final invocation.
        _pt_language = state.processing.get("current_language", "english")
        _pt_data_table = data_table
        _pt_last_exchange = format_message_history(state.processing.get("message_history", []), max_tokens=2000)
        _pt_user_request = state.input["raw_user_input"]

        # --- Re-entry: consume any retry markers and inject into the prompt ---
        # Two failure modes funnel back through planning via the shared
        # ``planning_retries`` budget: choregraph runtime failure (set by
        # trigger_choregraph_run_node) and XSD validation failure (set by
        # the last entry of this node, below).
        choregraph_error = state.processing.pop("choregraph_error", None)
        xsd_error = state.processing.pop("xsd_error", None)
        if choregraph_error:
            logger().logp(WARNING, "Planning re-entry — previous choregraph runtime error")
            _pt_user_request += (
                f"\n\nThe previous transformation XML was syntactically valid but the Choregraph pipeline "
                f"execution failed with error: {choregraph_error}. Please adjust the transformation to avoid "
                f"this runtime error."
            )
        if xsd_error:
            logger().logp(WARNING, "Planning re-entry — previous XSD validation error")
            _pt_user_request += f"\n\nPrevious attempt failed validation: {xsd_error}. Please fix the XML structure and respect the schema."

        # --- Check for returning clarification ---
        user_clarification = state.processing.pop("user_clarification", None)
        if user_clarification:
            # User answered — reset the consecutive counter now, before the LLM call
            state.processing["consecutive_clarifications"] = 0
            # Discard the stored raw AI response: it contained the structured JSON
            # from the early-exit call (with plan: null, early_exit: true) and would
            # bias the LLM into reproducing the same null plan via prior_messages.
            # The clarification context is already injected textually in user_prompt.
            state.processing.pop("last_transformation_ai_response", None)
            # Retrieve the original suggestions so the LLM knows what options were offered
            original_suggestions = state.processing.pop("clarification_suggestions", "")
            # Always append clarification to user_prompt so the LLM sees it as a clear instruction
            suggestions_context = ""
            if original_suggestions:
                suggestions_context = f"The options you proposed were:\n{original_suggestions}\n\n"
                logger().logp(DEBUG, f"Suggestions context for LLM after clarification: {suggestions_context}")
            _pt_user_request += (
                f"\n\n--- IMPORTANT: CLARIFICATION FROM USER ---\n"
                f"You previously asked the user for clarification about their request. "
                f"{suggestions_context}"
                f"The user has responded with the following selection/clarification:\n"
                f'"{user_clarification}"\n'
                f"You MUST now proceed with this clarification and complete ALL steps: "
                f"generate the visualization_plan (Step 2), the transformation XML (Step 3), and all other output fields. "
                f"Do NOT ask for further clarification (set early_exit to false)."
            )
        # --- Clarification counter: forbid early_exit after 2 consecutive clarifications ---
        clarif_count = state.processing.get("consecutive_clarifications", 0)
        forbid_early_exit = clarif_count >= 2
        if forbid_early_exit:
            logger().logp(INFO, f"Clarification limit reached ({clarif_count} consecutive). Forcing no early_exit.")
            _pt_user_request += "\n\n**CRITICAL OVERRIDE: You have already asked the user for clarification multiple times. You MUST NOT set early_exit to true. Proceed with your best interpretation of the request and generate the transformation XML.**"

        def _record_planning_retries(retries: int) -> None:
            tm = get_turn_metrics()
            if tm:
                tm.record_retries("Planning Transformation", retries)

        # Single budget for every LLM call through this node. Incremented
        # on *every* entry that makes an LLM call — initial attempt AND
        # automatic retries. Clarification replies are the one exception
        # (they're user-initiated, bounded separately by
        # ``consecutive_clarifications``) and must NOT spend the budget.
        is_clarification_reply = bool(state.processing.get("user_clarification"))
        if not is_clarification_reply:
            state.processing["planning_retries"] = state.processing.get("planning_retries", 0) + 1
        attempt_idx = state.processing.get("planning_retries", 0)

        # --- Single LLM call per node entry (no internal retry loop) ---
        llm_cfg, node_cfg = get_call_config("planning_transformation", config)
        chat_template, variables =PlanningTransformationNormal().build(
            language=_pt_language,
            data_table=_pt_data_table,
            last_exchange=_pt_last_exchange,
            user_request=_pt_user_request,
        )
        try:
            response, raw_ai_message = await self.llm_manager.ainvoke(
                chat_template=chat_template,
                variables=variables,
                llm_config=llm_cfg,
                response_schema=TransformationOutput,
                cache_name="planning_transformation",
                cost_label='Transformation XML Generation',
                max_tokens=3000,
                return_raw=True,
                **node_cfg,
            )
        except Exception as e:
            logger().logp(ERROR, f"Critical error during planning LLM call (attempt {attempt_idx}): {e}")
            state.processing["transformation_failed"] = True
            _write_transformation_comments(f"[FAILED TRANSFORMATION] {e}")
            _record_planning_retries(attempt_idx)
            return state

        if response is None:
            logger().logp(ERROR, f"Planning LLM returned no parsed response (attempt {attempt_idx}).")
            state.processing["transformation_failed"] = True
            _write_transformation_comments("[FAILED TRANSFORMATION] structured output unavailable")
            _record_planning_retries(attempt_idx)
            return state

        logger().logp(DEBUG, f"Planning LLM response — transformation_xml={bool(response.transformation_xml)}, plan={bool(response.plan)}")

        # --- Branch 1: clarification requested ---
        if response.early_exit:
            if forbid_early_exit:
                plan = f"**Transformation Plan:** {response.plan.transformation_plan}\n**Visualization Plan:** {response.plan.visualization_plan}" if response.plan else ""
                logger().logp(WARNING, "LLM attempted early_exit despite override. Ignoring — proceeding with best effort.")
                if not (response.transformation_xml and response.transformation_xml.strip()):
                    logger().logp(WARNING, "No transformation XML generated despite early_exit override.")
                    _restore_inputs_visibility()
                    state.processing["transformation_failed"] = False
                    _write_transformation_comments(response.comments or "")
                    state.processing["plan"] = plan
                    state.processing["consecutive_clarifications"] = 0
                    _record_planning_retries(attempt_idx)
                    return state
                # else: fall through to normal XML processing below
            else:
                logger().logp(INFO, "=== Transformation early exit (clarification needed) ===")
                state.processing['list_steps'].remove('transformation_feedback')
                state.processing['list_steps'].append('transformation_clarification')
                tag_current_trace(["request"] + state.processing['list_steps'])
                state.processing["transformation_failed"] = True
                _write_transformation_comments(response.comments or "")
                state.processing["consecutive_clarifications"] = clarif_count + 1
                state.processing["pending_clarification"] = {
                    "feedback_text": response.feedback_text or "",
                    "selection_prompt": response.selection_prompt,
                    "comments": response.comments or "",
                }
                state.processing["clarification_suggestions"] = (
                    response.selection_prompt.model_dump_json(indent=2)
                    if response.selection_prompt else ""
                )
                _record_planning_retries(attempt_idx)
                return state

        # --- Branch 2: no XML AND no plan → treat as "no transformation needed" ---
        if (not response.transformation_xml or not response.transformation_xml.strip()) and (
            response.plan is None or not response.plan.transformation_plan or not response.plan.transformation_plan.strip()
        ):
            plan = f"**Transformation Plan:** {response.plan.transformation_plan}\n**Visualization Plan:** {response.plan.visualization_plan}" if response.plan else ""
            logger().logp(WARNING, "LLM did not return any transformation XML.")
            _restore_inputs_visibility()
            state.processing["transformation_failed"] = False
            _write_transformation_comments(response.comments or "")
            state.processing["plan"] = plan or ""
            _record_planning_retries(attempt_idx)
            return state

        # --- Branch 3: has plan but no XML → one fallback LLM call, then commit ---
        if (not response.transformation_xml or not response.transformation_xml.strip()) and response.plan and response.plan.transformation_plan:
            logger().logp(WARNING, "LLM did not return XML but provided a plan. Running one fallback LLM call.")
            fallback_user_request = (
                f"{state.input['raw_user_input']}\n\n"
                f"Transformation plan to implement:\n{response.plan.transformation_plan}"
            )
            fb_template, fb_vars = PlanningTransformationFallback().build(
                language=state.processing.get("current_language", "english"),
                data_table=data_table,
                user_request=fallback_user_request,
            )
            fallback_response = await self.llm_manager.ainvoke(
                chat_template=fb_template,
                variables=fb_vars,
                llm_config=llm_cfg,
                response_schema=FallbackTransformationOutput,
                cost_label='Transformation XML Generation (Fallback)',
                max_tokens=3000,
                **node_cfg,
            )
            if fallback_response and fallback_response.transformation_xml and fallback_response.transformation_xml.strip():
                response.transformation_xml = fallback_response.transformation_xml
            else:
                logger().logp(WARNING, "Fallback LLM call did not return XML — signalling XSD retry.")
                state.processing["xsd_error"] = "LLM did not return any transformation XML after the fallback prompt."
                state.processing["transformation_failed"] = False
                _record_planning_retries(attempt_idx)
                return state

        # --- Branch 4: validate + write the XML ---
        cleaned_xml = response.transformation_xml.replace("```xml", "").replace("```", "").strip()
        try:
            xml_doc = etree.fromstring(cleaned_xml.encode('utf-8'))
            xml_schema.assertValid(xml_doc)
        except etree.XMLSyntaxError as syntax_err:
            error_msg = f"XML Syntax Error: {syntax_err}"
            logger().logp(WARNING, error_msg)
            log_choregraph_error(error_msg, error_type="syntax", attempt=attempt_idx, room_id=state.input.get("room_id"))
            state.processing["xsd_error"] = error_msg
            state.processing["transformation_failed"] = False
            _record_planning_retries(attempt_idx)
            return state
        except etree.DocumentInvalid as validation_err:
            error_msg = f"XSD Validation Error: {validation_err}"
            logger().logp(WARNING, error_msg)
            log_choregraph_error(error_msg, error_type="xsd_validation", attempt=attempt_idx, room_id=state.input.get("room_id"))
            state.processing["xsd_error"] = error_msg
            state.processing["transformation_failed"] = False
            _record_planning_retries(attempt_idx)
            return state

        # Reconcile inputs: preserve all original inputs (with full paths),
        # only adopt visibility from AI.
        if original_choregraph_content:
            try:
                original_doc = etree.fromstring(original_choregraph_content.encode('utf-8'))
                ai_visibility = {
                    inp.get('id'): inp.get('visibility', 'false')
                    for inp in xml_doc.findall('inputs/input')
                    if inp.get('id')
                }
                original_inputs_elem = original_doc.find('inputs')
                ai_inputs_elem = xml_doc.find('inputs')
                if original_inputs_elem is not None and ai_inputs_elem is not None:
                    for child in list(ai_inputs_elem):
                        ai_inputs_elem.remove(child)
                    for orig_inp in original_inputs_elem:
                        inp_copy = copy.deepcopy(orig_inp)
                        inp_id = inp_copy.get('id')
                        if inp_id in ai_visibility:
                            inp_copy.set('visibility', ai_visibility[inp_id])
                        ai_inputs_elem.append(inp_copy)
            except Exception as reconcile_err:
                logger().logp(WARNING, f"Input reconciliation failed, using AI inputs as-is: {reconcile_err}")

        try:
            pretty_xml = etree.tostring(xml_doc, pretty_print=True, xml_declaration=True, encoding="utf-8").decode("utf-8")
            with open(choregraph_xml_path, "w", encoding="utf-8") as f:
                f.write(pretty_xml)
        except Exception as write_err:
            logger().logp(ERROR, f"Error writing choregraph.xml: {write_err}")

        state.processing["transformation_xml"] = cleaned_xml

        if response.transformation_failed:
            _write_transformation_comments("[FAILED TRANSFORMATION]" + (response.comments or ""))
            state.processing["transformation_failed"] = True
            _record_planning_retries(attempt_idx)
            return state

        plan = f"**Transformation Plan:** {response.plan.transformation_plan}\n**Visualization Plan:** {response.plan.visualization_plan}" if response.plan else ""
        _write_transformation_comments(response.comments or "")
        state.processing["transformation_failed"] = False
        state.processing["plan"] = plan or ""
        state.processing["consecutive_clarifications"] = 0
        _record_planning_retries(attempt_idx)
        return state

    async def trigger_choregraph_run_node(self, state):
        """Execute (web) or defer to the client (SDK) the choregraph pipeline.

        Two paths, no shared pre-interrupt work:

        * ``is_api=True`` (SDK): ``interrupt()`` pauses the graph. The SDK
          runs choregraph locally and resumes via ``/ai/sdk/process``; on
          resume ``interrupt()`` returns immediately and we proceed to
          the downstream fan-out.
        * Web: POST ``/viz/run_choregraph``. On success → proceed. On
          failure → record ``choregraph_error`` so ``route_after_choregraph``
          can cycle back to ``planning_transformation_node`` (which owns
          the unified ``planning_retries`` counter) or forward to
          ``feedback_node`` when the budget is exhausted.

        The same XML is **never** retried: a cycle-back runs planning
        again, which always produces a fresh LLM call.

        Re-entry after the SDK interrupt returns this function to the
        top on resume; both branches above are idempotent from that
        second entry.
        """
        logger().logp(DEBUG, "[NODE] trigger_choregraph_run_node entered")

        logger().logp(DEBUG, f"Choregraph XML to run:\n{state.processing.get('transformation_xml', '')}")
        logger().logp(DEBUG, f"Plan: \n{state.processing.get('plan', '')}")
        if state.input.get("is_api"):
            # SDK path: pause. The SDK runs choregraph locally and resumes
            # after uploading post-transform artifacts.
            interrupt({"reason": "awaiting_sdk_choregraph"})
            return state

        # Web path — clear any prior-cycle error marker so route_after_choregraph
        # can distinguish success from a stale failure.
        state.processing.pop("choregraph_error", None)

        await self._post_stage(state.input["room_token"], "choregraph_run", "Transformation Running")

        payload = {
            "room_id": state.input["room_id"],
            "owner_id": state.input["owner_id"],
        }
        url = f"https://{SERVER_HOST}:{SERVER_PORT}/viz/run_choregraph"

        error: str = ""
        try:
            response = await self.http_client.post(url, json=payload, timeout=120.0)
            if response.status_code == 200:
                result = response.json()
                if result.get("status") == "ok":
                    return state
                error = result.get("error", "Unknown error")
            else:
                error = f"HTTP {response.status_code}: {response.text}"
                logger().logp(ERROR, f"Failed to trigger Choregraph run: {error}")
        except Exception as e:
            logger().logp(ERROR, f"Error triggering Choregraph run: {e}")
            error = str(e)

        # Record the error. The counter is bumped on the next planning
        # entry (single source of truth for budget accounting). If we're
        # at the cap already, route_after_choregraph will forward to
        # feedback_node and we surface the error into feedback_material
        # here so the feedback LLM can explain it to the user.
        state.processing["choregraph_error"] = error
        retries_so_far = state.processing.get("planning_retries", 0)
        log_choregraph_error(error, error_type="runtime", attempt=retries_so_far, room_id=state.input.get("room_id"))

        from .workflow_request import MAX_PLANNING_RETRIES
        if retries_so_far >= MAX_PLANNING_RETRIES:
            logger().logp(
                WARNING,
                f"Planning budget exhausted after {retries_so_far} retries; last choregraph error: {error}",
            )
            fm = dict(state.processing.get("feedback_material", {}) or {})
            fm["ai_processing"] = (
                f"The data transformation pipeline failed and the retry budget is exhausted. "
                f"Last error: {error}"
            )
            state.processing["feedback_material"] = fm
        return state
