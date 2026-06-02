# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Chat-template-native prompt system.

Each logical prompt (entrypoint_classification, feedback, etc.) is a
chat-type prompt stored in Langfuse and mirrored in prompt_templates.yaml
as the fallback source. The `Prompt` base class fetches a
`ChatPromptTemplate` directly, attaches Langfuse linking metadata on the
template (not the LLM invoke config — the only way Langfuse's LangChain
handler actually links generations to prompt versions).

Each subclass declares its Langfuse name and overrides `prepare_vars` to
return the dict of variables the template expects. No string assembly,
no format_map hacks — substitution is 100% LangChain-native at
`chain.ainvoke(vars)` time.

Runtime behaviour:
- LANGFUSE_TRACING=1 → fetch chat prompt from Langfuse (5s cache TTL in
  dev, 60s default), yaml as SDK fallback on unreachable/missing.
- Otherwise → yaml-only. Pure file-based, no Langfuse import reached.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Optional

import yaml
from langchain_core.prompts import ChatPromptTemplate
from logger import DEBUG, ERROR, INFO, WARNING, logger
from lxml import etree

from .config import (
    FAQ_FILEPATH,
    PROMPT_TEMPLATES_PATH,
    USE_YAML_SCHEMA,
    XSD_FILEPATH,
)
from .xsd_to_yaml import convert_xsd_to_yaml

# ---------------------------------------------------------------------------
# Derived-data cache (warmed at startup)
# ---------------------------------------------------------------------------
_prompt_cache: dict[str, str] = {}


def _read_and_convert_visuspec_xsd() -> str:
    try:
        with open(XSD_FILEPATH, "r", encoding="utf-8") as f:
            xsd_content = f.read()
        cleaned = re.sub(r"<!--TODO\s*:.*?-->", "", xsd_content, flags=re.DOTALL)
    except FileNotFoundError:
        raise FileNotFoundError(f"XSD file '{XSD_FILEPATH}' not found.")
    return convert_xsd_to_yaml(cleaned) if USE_YAML_SCHEMA else cleaned


def _read_and_convert_choregraph_xsd() -> str:
    try:
        from choregraph import Choregraph as CG
        xsd_content = CG().get_xsd()
        cleaned = re.sub(r"<!--TODO\s*:.*?-->", "", xsd_content, flags=re.DOTALL)
    except Exception as e:
        logger().logp(ERROR, f"Could not load TransformGraph XSD from Choregraph: {e}")
        return ""
    return convert_xsd_to_yaml(cleaned) if (USE_YAML_SCHEMA and cleaned) else cleaned


def _read_exclusion_enums() -> str:
    ns = {"xs": "http://www.w3.org/2001/XMLSchema"}
    exclude = {"UNDEFINED", "NONE", "CUSTOM"}
    simple_type_map = {
        "colorPalette": "ColorPaletteName",
        "colorPaletteType": "ColorPaletteCategory",
        "scaleType": "ScaleType",
        "interpolation": "interpolation",
    }
    tree = etree.parse(XSD_FILEPATH)
    root = tree.getroot()
    enums: dict[str, list[str]] = {}
    for section, st_name in simple_type_map.items():
        st = root.find(f".//xs:simpleType[@name='{st_name}']", ns)
        enums[section] = (
            [e.get("value") for e in st.findall(".//xs:restriction/xs:enumeration", ns)
             if e.get("value") not in exclude] if st is not None else []
        )
    marks_ct = root.find(".//xs:complexType[@name='Marks']/xs:choice", ns)
    enums["markType"] = (
        [e.get("name") for e in marks_ct.findall("xs:element", ns)
         if e.get("name") not in exclude] if marks_ct is not None else []
    )
    for k in enums:
        enums[k] = sorted(enums[k], key=str.lower)
    lines: list[str] = []
    for section, values in enums.items():
        lines.append(f"- {section}: ")
        lines.extend(f"  {v}" for v in values)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _read_faq() -> str:
    try:
        with open(FAQ_FILEPATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger().logp(WARNING, f"FAQ file '{FAQ_FILEPATH}' not found.")
        return ""


# ---------------------------------------------------------------------------
# Langfuse integration (opt-in via LANGFUSE_TRACING=1)
# ---------------------------------------------------------------------------
def _langfuse_enabled() -> bool:
    return os.getenv("LANGFUSE_TRACING", "").lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Circuit breaker — fail-fast when Langfuse is unreachable
# ---------------------------------------------------------------------------
# A single failed `get_prompt` (DNS error, timeout) costs ~10s of SDK-internal
# retries, and the SDK does NOT cache fallback results — so without this every
# prompt of every node would re-pay the full retry storm. Once any fetch falls
# back, we treat Langfuse as down for a cooldown window and serve yaml directly,
# bounding the cost to at most one slow call per `LANGFUSE_DOWN_COOLDOWN`.
_LF_DOWN_UNTIL: float = 0.0  # monotonic deadline; Langfuse skipped until then


def _lf_down_cooldown_seconds() -> int:
    raw = os.getenv("LANGFUSE_DOWN_COOLDOWN")
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return 60


def _lf_is_down() -> bool:
    return time.monotonic() < _LF_DOWN_UNTIL


def _lf_mark_down(reason: str) -> None:
    """Open the circuit for the cooldown window. Logs once per transition."""
    global _LF_DOWN_UNTIL
    was_up = not _lf_is_down()
    cooldown = _lf_down_cooldown_seconds()
    _LF_DOWN_UNTIL = time.monotonic() + cooldown
    if was_up:
        logger().logp(
            WARNING,
            f"Langfuse unreachable ({reason}); serving prompts from yaml for "
            f"{cooldown}s (tune via LANGFUSE_DOWN_COOLDOWN).",
        )


def _langfuse_client():
    if not _langfuse_enabled() or _lf_is_down():
        return None
    try:
        from langfuse import get_client
        return get_client()
    except Exception as e:
        logger().logp(DEBUG, f"Langfuse client unavailable: {e}")
        return None


def _langfuse_prompt_label() -> str:
    return os.getenv("LANGFUSE_PROMPT_LABEL", "latest")


def _prompt_cache_ttl_seconds() -> int:
    explicit = os.getenv("LANGFUSE_PROMPT_CACHE_TTL")
    if explicit:
        try:
            return int(explicit)
        except ValueError:
            pass
    return 5 if _langfuse_enabled() else 60


# ---------------------------------------------------------------------------
# Prompt base class — chat-template-first, Langfuse-native
# ---------------------------------------------------------------------------
class Prompt:
    """Base class: one concrete subclass per Langfuse chat prompt.

    Subclasses set:
      - LANGFUSE_NAME: canonical prompt name, e.g. 'feedback'.

    Subclasses override:
      - prepare_vars(**kwargs) -> dict: compute the template variables.

    Call sites use a single entry point:
        template, variables, lf_ref = PromptSubclass().build(**context)
    Then hand that to llm_manager.ainvoke_chat.
    """

    LANGFUSE_NAME: str = ""
    _templates: dict[str, Any] = {}   # yaml fallback store

    # ---------- classmethods ----------
    @classmethod
    def load_templates(cls) -> None:
        path = Path(PROMPT_TEMPLATES_PATH)
        with open(path, "r", encoding="utf-8") as f:
            cls._templates = yaml.safe_load(f)
        cls.warm_caches()

    @classmethod
    def warm_caches(cls) -> None:
        _prompt_cache["visuspec_schema"] = _read_and_convert_visuspec_xsd()
        _prompt_cache["choregraph_schema"] = _read_and_convert_choregraph_xsd()
        _prompt_cache["exclusion_enums"] = _read_exclusion_enums()
        _prompt_cache["faq_content"] = _read_faq()

    # ---------- instance ----------
    def __init__(self):
        if not self.LANGFUSE_NAME:
            raise NotImplementedError(f"{type(self).__name__} must set LANGFUSE_NAME")
        if not self._templates:
            raise RuntimeError("Templates not loaded. Call Prompt.load_templates() first.")
        # Both Langfuse and yaml use the same canonical name for the prompt.
        self._local_key = self.LANGFUSE_NAME

    def _yaml_messages(self) -> list[dict]:
        """Return the raw messages list from yaml (type=chat). For fallback."""
        entry = self._templates.get(self._local_key)
        if not entry or "messages" not in entry:
            raise KeyError(
                f"yaml has no chat entry for '{self._local_key}' (expected type=chat)"
            )
        return entry["messages"]

    def _build_chat_template_from_messages(self, messages: list[dict]) -> ChatPromptTemplate:
        """Build a ChatPromptTemplate from yaml-fallback messages.

        Must produce the exact same f-string-ready text that
        `ChatPromptClient.get_langchain_prompt()` produces when Langfuse IS
        reachable — otherwise yaml-fallback and live-Langfuse paths would
        diverge on edge cases (JSON examples, DSL literal braces, etc).
        We delegate to Langfuse SDK's static helper to guarantee parity.
        """
        from langfuse.model import BasePromptClient
        tuples = [
            (m["role"], BasePromptClient._get_langchain_prompt_string(m["content"]))
            for m in messages
        ]
        return ChatPromptTemplate.from_messages(tuples)

    def _fetch_chat_template(self) -> tuple[ChatPromptTemplate, Optional[Any]]:
        """Return (template, langfuse_prompt_obj).
        langfuse_prompt_obj is None when yaml fallback is used.

        The Langfuse prompt object is attached as `metadata={"langfuse_prompt": p}`
        on the ChatPromptTemplate itself (per Langfuse docs). The handler's
        `_register_langfuse_prompt` fires on the template's `on_chain_start`
        event with the metadata visible, registering the link for the
        generation that follows in the chain.
        """
        lf = _langfuse_client()
        yaml_msgs = self._yaml_messages()
        if lf is not None:
            try:
                p = lf.get_prompt(
                    self.LANGFUSE_NAME,
                    label=_langfuse_prompt_label(),
                    cache_ttl_seconds=_prompt_cache_ttl_seconds(),
                    type="chat",
                    fallback=yaml_msgs,
                )
                if not getattr(p, "is_fallback", False):
                    # Use Langfuse's canonical LangChain integration helper:
                    # `get_langchain_prompt()` returns f-string-ready
                    # messages (mustache `{{var}}` → `{var}`, JSON-shaped
                    # braces auto-escaped, DSL literals `{{mark:..}}`
                    # preserved as `{{mark:..}}` which f-string reads as
                    # literal `{mark:..}`).  Attach prompt metadata at
                    # construction so Langfuse's handler links generations.
                    base = ChatPromptTemplate.from_messages(
                        p.get_langchain_prompt()
                    )
                    tmpl = ChatPromptTemplate(
                        messages=base.messages,
                        metadata={"langfuse_prompt": p},
                    )
                    return tmpl, p
                # Fallback returned => Langfuse couldn't serve a real prompt
                # (unreachable, or prompt missing). Open the circuit so the
                # rest of this request skips the retry storm.
                _lf_mark_down(f"get_prompt '{self.LANGFUSE_NAME}' returned fallback")
                logger().logp(DEBUG, f"Prompt '{self.LANGFUSE_NAME}' served from yaml fallback")
            except Exception as e:
                _lf_mark_down(f"get_prompt '{self.LANGFUSE_NAME}' raised: {e}")
                logger().logp(WARNING, f"Langfuse get_prompt '{self.LANGFUSE_NAME}' failed ({e}); using yaml")
        return self._build_chat_template_from_messages(yaml_msgs), None

    def prepare_vars(self, **kwargs) -> dict:
        """Subclass computes the variables the template expects.
        Default: pass-through (only valid when template has no variables)."""
        return dict(kwargs)

    @classmethod
    def fragment(cls, category: str, key: str) -> str:
        """Fetch a shared text fragment (tone blurb, step hint, action label,
        addendum…) by (category, key).

        Storage: `shared/{category}/{key}` as a text-type Langfuse
        prompt when tracing is on; yaml fallback via the nested
        `_fragments` section otherwise. Enables non-engineer iteration on
        these content pieces from the Langfuse UI without code changes.
        """
        fragments = cls._templates.get("_fragments") or {}
        category_map = fragments.get(category, {})
        # If the key isn't declared in yaml, the fragment is not defined for
        # this step/tone — return empty silently (no Langfuse round-trip,
        # no 404 noise).
        if key not in category_map:
            return ""
        yaml_text = category_map[key]
        lf = _langfuse_client()
        if lf is None:
            return yaml_text
        name = f"shared/{category}/{key}"
        try:
            p = lf.get_prompt(
                name,
                label=_langfuse_prompt_label(),
                cache_ttl_seconds=_prompt_cache_ttl_seconds(),
                fallback=yaml_text,
            )
            if getattr(p, "is_fallback", False):
                _lf_mark_down(f"fragment '{name}' returned fallback")
                return yaml_text
            return p.prompt
        except Exception as e:
            _lf_mark_down(f"fragment '{name}' raised: {e}")
            logger().logp(WARNING, f"Langfuse fragment '{name}' failed ({e}); using yaml")
            return yaml_text

    def build(self, **kwargs) -> tuple[ChatPromptTemplate, dict]:
        """Full entry point for call sites.

        Returns: (chat_template, variables).
        The template already carries `metadata={"langfuse_prompt": ...}`
        internally (set in `_fetch_chat_template` when Langfuse is reached),
        so generations link automatically when invoked through the chain.
        """
        template, _lf_ref = self._fetch_chat_template()
        variables = self.prepare_vars(**kwargs)
        return template, variables


# ---------------------------------------------------------------------------
# Concrete prompt subclasses — one per Langfuse chat prompt
# ---------------------------------------------------------------------------
class EntrypointClassification(Prompt):
    LANGFUSE_NAME = "entrypoint_classification"

    def prepare_vars(self, message: str, latest_ai_response: str = "", **_) -> dict:
        return {"message": message, "latest_ai_response": latest_ai_response}


class XMLGeneration(Prompt):
    LANGFUSE_NAME = "xml_generation"

    def prepare_vars(
        self,
        user_request: str,
        data_stats: str,
        visualization_plan: str = "",
        **_,
    ) -> dict:
        return {
            "schema_content": _prompt_cache.get("visuspec_schema") or _read_and_convert_visuspec_xsd(),
            "user_request": user_request,
            "data_stats": data_stats,
            "visualization_plan": visualization_plan,
        }


class KeywordClassification(Prompt):
    LANGFUSE_NAME = "keyword_classification"

    def prepare_vars(
        self,
        user_message: str,
        complementary_information: Optional[str] = None,
        **_,
    ) -> dict:
        # Contextual addition concatenated to user message if present
        user_message_final = user_message
        if complementary_information:
            user_message_final = (
                f"{user_message}\n"
                f"Contextual information regarding the request:\n{complementary_information}\n"
            )
        return {"user_message": user_message_final}


class ExclusionProcessing(Prompt):
    LANGFUSE_NAME = "exclusion_processing"

    def prepare_vars(self, **kwargs) -> dict:
        # The exclusion user template takes whatever kwargs the caller passes.
        # The system template depends on enum_definitions (pre-computed).
        return {
            "enum_definitions": _prompt_cache.get("exclusion_enums") or _read_exclusion_enums(),
            **kwargs,
        }


class PlanningTransformationNormal(Prompt):
    LANGFUSE_NAME = "planning_transformation_normal"

    def prepare_vars(self, **kwargs) -> dict:
        # `xml_mapping_rules` is NOT here: it's composed in via Langfuse's
        # `@@@langfusePrompt:name=shared/xml_mapping_rules@@@` reference,
        # which Langfuse resolves server-side before returning the prompt.
        return {
            "viz_schema_content": _prompt_cache.get("visuspec_schema") or _read_and_convert_visuspec_xsd(),
            "transformation_schema_content": _prompt_cache.get("choregraph_schema") or _read_and_convert_choregraph_xsd(),
            **kwargs,
        }


class PlanningTransformationFallback(Prompt):
    LANGFUSE_NAME = "planning_transformation_fallback"

    def prepare_vars(self, **kwargs) -> dict:
        return {
            "transformation_schema_content": _prompt_cache.get("choregraph_schema") or _read_and_convert_choregraph_xsd(),
            **kwargs,
        }


# -- Feedback with tone / hints / addendum variable preparation ---------------

# All tone blurbs, step-action labels, step-hints and the color-palette
# addendum live in Langfuse (at `shared/{category}/{key}`) and mirror
# to `_fragments` in prompt_templates.yaml for staging/prod fallback. Look
# them up via `Prompt.fragment(category, key)`.


class FeedbackMessage(Prompt):
    LANGFUSE_NAME = "feedback"

    # Background context carried from previous turns; surfaced to the LLM in a
    # dedicated "silent context" block rather than the current-turn events,
    # so the model can use it when relevant without acknowledging it.
    _SILENT_CONTEXT_KEYS = ("persistent_additional_information", "last_viz_summary")

    def prepare_vars(
        self,
        list_steps: list[str],
        personality_tone: str = "friendly",
        feedback_material: dict = None,
        data_stats: str = "",
        last_exchange: str = "",
        **_,
    ) -> dict:
        feedback_material = feedback_material or {}

        # Fallback / degraded case
        if "fallback" in list_steps or not list_steps:
            return {
                "personality_placeholder": "",
                "actions_placeholder": "your message",
                "step_hints": "",
                "structural_addendum": "",
                "visualization_placeholder": "{visualization_placeholder}",
                "feedback_material": (
                    "Gently inform the user that their request could not be processed due to "
                    "insufficient or unclear information. Encourage clarification."
                ),
                "silent_context": "(none)",
                "data_stats": data_stats,
                "last_exchange": last_exchange,
            }

        # All content fragments below are fetched via Prompt.fragment(), which
        # reads from Langfuse (`shared/{category}/{key}`) when tracing
        # is enabled and falls back to yaml otherwise. No hardcoded strings.
        actions = [self.fragment("step_actions", s) for s in list_steps]
        actions = [a for a in actions if a]
        actions_text = (
            ", ".join(actions[:-1]) + " and " + actions[-1] if len(actions) > 1 else (actions[0] if actions else "")
        )

        # One fragment() lookup per step (was called twice — in the `if` and
        # the f-string — doubling Langfuse round-trips per step).
        hints = []
        for s in list_steps:
            hint = self.fragment("step_hints", s)
            if hint:
                hints.append(f"- {hint}")
        step_hints_text = "**Step guidance:**\n" + "\n".join(hints) if hints else ""

        structural_addendum = ""
        if "color_palette_request" in list_steps:
            structural_addendum = self.fragment("addenda", "color_palette")

        # Compose user-side feedback_material text
        assembled: list[str] = []
        silent: list[str] = []
        if "viz_building_err" in feedback_material:
            fm_text = f"--- viz_building_err ---\n{feedback_material['viz_building_err']}\n"
        else:
            for log_type, content in feedback_material.items():
                if log_type in self._SILENT_CONTEXT_KEYS:
                    if content:
                        silent.append(f"--- {log_type} ---\n{content}\n")
                    continue
                if log_type == "asp_failed":
                    assembled.append(
                        "--- asp_failed ---\nasp_failed: True. The visualization generation FAILED. "
                        "Do NOT invent data values.\n"
                    )
                    continue
                if log_type == "user_question":
                    content = _build_question_answer_block(content)
                assembled.append(f"--- {log_type} ---\n{content}\n")
            fm_text = "\n".join(assembled)

        silent_context = "\n".join(silent) if silent else "(none)"

        return {
            "personality_placeholder": self.fragment("tones", personality_tone),
            "actions_placeholder": actions_text,
            "step_hints": step_hints_text,
            "structural_addendum": structural_addendum,
            "visualization_placeholder": "{visualization_placeholder}",
            "feedback_material": fm_text,
            "silent_context": silent_context,
            "data_stats": data_stats,
            "last_exchange": last_exchange,
        }




def _build_question_answer_block(user_question: dict) -> str:
    """Expand a user_question classification dict into a readable text block."""
    additions = ""
    company_related = user_question.get("company_related") or ""
    if isinstance(company_related, str) and company_related.strip():
        faq = Prompt.fragment("knowledge", "faq")
        if faq:
            additions += (
                f"\nHere is some information about NVEIL that may help you answer the user's question:\n"
                f"---\n{faq}\n---\n"
            )
    joined = "; ".join(v for v in user_question.values() if v)
    core = f"User question: {joined}\n" if joined else ""
    return core + additions


class CSVCharacterization(Prompt):
    LANGFUSE_NAME = "csv_characterization"

    def prepare_vars(self, sample: str, **_) -> dict:
        return {"sample": sample}


class SampleCreation(Prompt):
    LANGFUSE_NAME = "sample_creation"

    def prepare_vars(self, dataset_columns: str, examples: str, **_) -> dict:
        return {
            "schema_content": _prompt_cache.get("visuspec_schema") or _read_and_convert_visuspec_xsd(),
            "dataset_columns": dataset_columns,
            "examples": examples,
        }


# ---------------------------------------------------------------------------
# Boot-time seeding — push yaml prompts that are absent from Langfuse
# ---------------------------------------------------------------------------
# Mirrors scripts/seed_langfuse_prompts.py, but idempotent (seed-if-missing,
# never bumps an existing version) and safe to run at every boot: it fails fast
# when Langfuse is unreachable so a down host never blocks startup. The manual
# script remains the tool for a deliberate, version-bumping reseed.
_SEED_YAML_ONLY_SECTIONS = ("_xml_mapping_rules", "question_answering")


def _langfuse_reachable(timeout: float = 3.0) -> bool:
    """Fast health probe against LANGFUSE_HOST. A raw httpx GET fails almost
    instantly on DNS errors, unlike the SDK's ~10s retry storm."""
    host = os.getenv("LANGFUSE_HOST")
    if not host:
        return False
    try:
        import httpx
        r = httpx.get(f"{host.rstrip('/')}/api/public/health", timeout=timeout)
        return r.status_code < 500
    except Exception as e:
        logger().logp(DEBUG, f"Langfuse health probe failed: {e}")
        return False


def _lf_prompt_exists(client, name: str, *, is_chat: bool) -> bool:
    """True if Langfuse already serves a real (non-fallback) prompt by this
    name. Uses a throwaway fallback so a missing prompt returns is_fallback=True
    rather than raising."""
    try:
        kwargs: dict[str, Any] = {"label": _langfuse_prompt_label(), "cache_ttl_seconds": 0}
        if is_chat:
            kwargs["type"] = "chat"
            kwargs["fallback"] = [{"role": "system", "content": "_probe"}]
        else:
            kwargs["fallback"] = "_probe"
        p = client.get_prompt(name, **kwargs)
        return not getattr(p, "is_fallback", False)
    except Exception:
        return False


def seed_langfuse_prompts_if_missing(label: Optional[str] = None) -> None:
    """Best-effort: create in Langfuse any yaml prompt/fragment that isn't there
    yet. Idempotent — existing prompts are left untouched (no version bump), so
    this is safe to call on every startup. Returns immediately and quietly when
    tracing is off or the host is unreachable.
    """
    if not _langfuse_enabled():
        return
    if not Prompt._templates:
        logger().logp(DEBUG, "Seed skipped: prompt templates not loaded.")
        return
    if not _langfuse_reachable():
        _lf_mark_down("boot seed: health probe failed")
        logger().logp(
            WARNING,
            "Langfuse unreachable at boot; skipping prompt seeding "
            "(prompts will use yaml fallback until it recovers).",
        )
        return

    client = _langfuse_client()
    if client is None:
        return
    label = label or _langfuse_prompt_label()
    templates = Prompt._templates
    created_chat = 0
    created_frag = 0

    for name, entry in templates.items():
        if name == "_fragments" or name in _SEED_YAML_ONLY_SECTIONS:
            continue
        if not isinstance(entry, dict) or entry.get("type") != "chat":
            continue
        if _lf_prompt_exists(client, name, is_chat=True):
            continue
        try:
            client.create_prompt(
                name=name,
                type="chat",
                prompt=[
                    {"role": m["role"], "content": m["content"]}
                    for m in entry.get("messages") or []
                ],
                labels=[label],
            )
            created_chat += 1
        except Exception as e:
            logger().logp(WARNING, f"Langfuse seed of chat prompt '{name}' failed: {e}")

    fragments = templates.get("_fragments") or {}
    for category, items in fragments.items():
        for key, text in (items or {}).items():
            fname = f"shared/{category}/{key}"
            if _lf_prompt_exists(client, fname, is_chat=False):
                continue
            try:
                client.create_prompt(name=fname, type="text", prompt=text, labels=[label])
                created_frag += 1
            except Exception as e:
                logger().logp(WARNING, f"Langfuse seed of fragment '{fname}' failed: {e}")

    if created_chat or created_frag:
        logger().logp(
            INFO,
            f"Seeded Langfuse with {created_chat} chat prompt(s) and "
            f"{created_frag} fragment(s) at label '{label}'.",
        )
    else:
        logger().logp(DEBUG, "Langfuse prompts already present; nothing to seed.")
