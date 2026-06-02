# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Provider-agnostic LangChain-backed LLM manager.

Handles every provider supported by `init_chat_model`. No context-cache
support — providers that have a cache (currently only Gemini) get a
subclass that overrides `_resolve_llm_and_template`.

Hooks for subclasses:
- `_resolve_llm_and_template`: swap the LLM (e.g. bind a cache resource)
  and/or transform the template (e.g. strip system message) before the
  chain is built.
- `_record_cost`: provider-specific cost estimation; the base does
  nothing. Gemini overrides.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, ClassVar, Optional, Type

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from logger import DEBUG, ERROR, INFO, WARNING, logger
from pydantic import BaseModel

from shared.llm_config import LLMConfig, build_chat_model

from ..turn_metrics import get_turn_metrics
from .base import LLMManager


def _stable_repr(value: Any) -> str:
    """Hashable representation of a kwarg value for the LLM pool key."""
    if isinstance(value, dict):
        return repr(sorted(value.items()))
    if isinstance(value, (list, tuple)):
        return repr(list(value))
    return repr(value)


# Substrings that indicate "retrying with a different structured-output
# method or attempt won't help" — same auth/model error will recur.
_NON_RETRYABLE_HINTS = (
    "invalid api key",
    "incorrect api key",
    "unauthorized",
    "permission_denied",
    "401",
    "403",
    "model_not_found",
    "model not found",
    "does not exist",
    "404",
)


def _is_non_retryable_error(exc: Exception) -> bool:
    """True for auth / unknown-model errors that won't change on retry."""
    msg = str(exc).lower()
    return any(hint in msg for hint in _NON_RETRYABLE_HINTS)


class LangChainLLMManager(LLMManager):
    supports_context_cache: ClassVar[bool] = False
    supports_implicit_cache: ClassVar[bool] = False

    # Default instantiation policy: a single shared instance per concrete
    # subclass. Subclasses with per-config state (e.g. GeminiLLMManager's
    # cache scoped to a Google account) override `for_config`.
    _instance: ClassVar[Optional["LangChainLLMManager"]] = None

    def __init__(self):
        self._pool: dict[tuple, BaseChatModel] = {}

    @classmethod
    def for_config(cls, config: LLMConfig) -> "LangChainLLMManager":
        """Return a manager instance suitable for `config`.

        Default: lazily initialized singleton per concrete class. The
        config is unused at the manager level — `LangChainLLMManager`
        holds no per-config state (the BaseChatModel pool inside is
        keyed on the api_key hash, so users stay isolated).
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # LLM pool — keyed by (provider, model, api_key_hash, frozen kwargs).
    # api_key_hash is mandatory: pool entries must NOT be reused across
    # users (security + billing).
    # ------------------------------------------------------------------

    def _pool_key(self, config: LLMConfig, model: str, kwargs: dict) -> tuple:
        api_key_hash = hashlib.sha256(config.api_key.encode("utf-8")).hexdigest()[:12]
        kwargs_key = tuple(sorted((k, _stable_repr(v)) for k, v in kwargs.items()))
        # Key on the EFFECTIVE model (per-user override > yaml default), so
        # users overriding the model don't get a stale cached BaseChatModel
        # built with the yaml-default model name.
        effective_model = config.model_override or model
        return (config.provider, effective_model, config.base_url, api_key_hash, kwargs_key)

    def _get_chat_model(
        self, config: LLMConfig, model: str, **kwargs: Any
    ) -> BaseChatModel:
        key = self._pool_key(config, model, kwargs)
        cached = self._pool.get(key)
        if cached is not None:
            return cached
        instance = build_chat_model(config, model=model, **kwargs)
        self._pool[key] = instance
        return instance

    # ------------------------------------------------------------------
    # Subclass hooks
    # ------------------------------------------------------------------

    def _resolve_llm_and_template(
        self,
        chat_template: ChatPromptTemplate,
        variables: dict,
        llm_config: LLMConfig,
        model: str,
        cache_name: Optional[str],
        model_kwargs: dict,
    ) -> tuple[BaseChatModel, ChatPromptTemplate]:
        if cache_name and not self.supports_context_cache:
            logger().logp(
                DEBUG,
                f"cache_name={cache_name!r} ignored — provider "
                f"{llm_config.provider!r} has no context-cache support.",
            )
        return (
            self._get_chat_model(llm_config, model, **model_kwargs),
            chat_template,
        )

    def _record_cost(
        self,
        model: str,
        usage_metadata: dict,
        cost_label: Optional[str],
    ) -> None:
        # Base manager: no cost estimation. Gemini subclass overrides.
        return

    # ------------------------------------------------------------------
    # Response helpers (provider-agnostic)
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_content(content: Any) -> Any:
        """Extract plain text from possibly-structured content."""
        if isinstance(content, list):
            text_parts = [
                p["text"] for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            ]
            return " ".join(text_parts) if text_parts else str(content)
        return content

    @staticmethod
    def _extract_thinking(message: Any) -> Optional[str]:
        """Pull reasoning/thinking text out of an AIMessage.

        Tries `message.content_blocks` (LangChain v1 normalized accessor —
        Anthropic / OpenAI / Google all map to `{type: "reasoning"}`),
        then falls back to legacy Gemini list-of-parts format
        (`{type: "thinking"}`).
        """
        blocks = getattr(message, "content_blocks", None)
        if blocks:
            reasoning = [
                (b.get("reasoning") or b.get("thinking") or "")
                for b in blocks
                if isinstance(b, dict) and b.get("type") == "reasoning"
            ]
            joined = "\n".join(t for t in reasoning if t)
            if joined:
                return joined

        content = getattr(message, "content", None)
        if isinstance(content, list):
            parts = [
                p["thinking"] for p in content
                if isinstance(p, dict) and p.get("type") == "thinking"
            ]
            if parts:
                return "\n".join(parts)
        return None

    def _handle_structured_response(
        self,
        response: Any,
        response_schema: Type[BaseModel],
        model: str,
        cost_label: Optional[str],
        usage_metadata: dict,
    ):
        if isinstance(response, response_schema):
            self._record_cost(model, usage_metadata, cost_label)
            return response
        if isinstance(response, dict):
            logger().logp(
                WARNING,
                f"[{cost_label}] Got dict instead of "
                f"{response_schema.__name__}, attempting validation...",
            )
            validated = response_schema.model_validate(response)
            self._record_cost(model, usage_metadata, cost_label)
            return validated
        if response is None:
            raise ValueError(
                f"LLM returned None for [{cost_label}] "
                f"(model may have refused or produced empty output)."
            )
        logger().logp(
            ERROR,
            f"[{cost_label}] Unexpected response type: "
            f"{type(response).__name__}, content: {str(response)[:500]}",
        )
        raise ValueError(
            f"LLM response for [{cost_label}] step does not match the "
            f"expected schema (got {type(response).__name__})."
        )

    # ------------------------------------------------------------------
    # Async invocation
    # ------------------------------------------------------------------

    async def ainvoke(
        self,
        *,
        chat_template: ChatPromptTemplate,
        variables: dict,
        llm_config: LLMConfig,
        model: str,
        response_schema: Optional[Type[BaseModel]] = None,
        cost_label: Optional[str] = None,
        cache_name: Optional[str] = None,
        return_raw: bool = False,
        **model_kwargs: Any,
    ):
        llm, chat_template = self._resolve_llm_and_template(
            chat_template, variables, llm_config, model, cache_name, model_kwargs,
        )

        if response_schema is not None:
            return await self._ainvoke_structured(
                llm, chat_template, variables, response_schema,
                model, cost_label, return_raw,
            )
        if return_raw:
            raise ValueError("return_raw=True requires response_schema.")
        return await self._ainvoke_plain(
            llm, chat_template, variables, model, cost_label,
        )

    async def _ainvoke_structured(
        self,
        llm: BaseChatModel,
        chat_template: ChatPromptTemplate,
        variables: dict,
        response_schema: Type[BaseModel],
        model: str,
        cost_label: Optional[str],
        return_raw: bool,
    ):
        # Retry strategy — read this before changing the loop:
        #
        # - We try TWO structured-output methods in order: `json_schema`
        #   first (decoder-enforced — better quality on most providers),
        #   `function_calling` as a universal fallback (covers schemas
        #   with unions/optionals that don't round-trip through JSON
        #   Schema, and providers whose `json_schema` support is flaky:
        #   some OpenRouter routes, quantized open-weights models, …).
        #
        # - Each retry attempt runs the FULL pair (json_schema, then
        #   function_calling) — this is intentional: a transient hiccup
        #   in attempt N+1 with json_schema may succeed even if attempt N
        #   failed both. Worst case: max_retries × 2 LLM calls.
        #
        # - `_is_non_retryable_error` short-circuits the loop on auth /
        #   "model not found" errors: same key/model, both methods will
        #   fail identically — no point burning the rest of the budget.
        #
        # - Only `parsed is None` (model didn't respect schema) is treated
        #   as retry-worthy. Plain text is never an acceptable answer here.
        ORDERED_METHODS = ("json_schema", "function_calling")
        max_retries = 3
        for attempt in range(max_retries):
            for method in ORDERED_METHODS:
                try:
                    llm_structured = llm.with_structured_output(
                        response_schema, method=method, include_raw=True, strict=True
                    )
                    chain = chat_template | llm_structured
                    start = datetime.now()
                    response = await chain.ainvoke(variables)
                    elapsed_s = (datetime.now() - start).total_seconds()
                    logger().logp(
                        DEBUG,
                        f"⏱️ LLM call for [{cost_label}] "
                        f"(attempt {attempt + 1}, method={method}) "
                        f"took {elapsed_s:.2f}s.",
                    )
                    raw_ai_message = response.get("raw")
                    usage = (
                        dict(raw_ai_message.usage_metadata)
                        if raw_ai_message and raw_ai_message.usage_metadata
                        else {}
                    )
                    usage_metadata = {model: usage}
                    tm = get_turn_metrics()
                    if tm is not None:
                        tm.record(cost_label or "unknown", elapsed_s, usage)
                    thinking = (
                        self._extract_thinking(raw_ai_message)
                        if raw_ai_message else None
                    )
                    if thinking:
                        logger().logp(INFO, f"💭 [{cost_label}] Thinking:\n{thinking}")
                    parsed = self._handle_structured_response(
                        response["parsed"], response_schema, model,
                        cost_label, usage_metadata,
                    )
                    if return_raw:
                        return parsed, raw_ai_message
                    return parsed
                except Exception as e:
                    logger().logp(
                        WARNING,
                        f"⚠️ [{cost_label}] method={method} "
                        f"attempt {attempt + 1}/{max_retries}: {e}",
                    )
                    # Auth + unknown-model errors won't change on retry —
                    # bail out immediately rather than burning the full
                    # methods × attempts budget on guaranteed failures.
                    if _is_non_retryable_error(e):
                        logger().logp(
                            ERROR,
                            f"❌ [{cost_label}] non-retryable error "
                            f"({type(e).__name__}); aborting.",
                        )
                        if return_raw:
                            return None, None
                        return None
                    # Otherwise fall through to next method, then next attempt.
                    continue
        logger().logp(
            ERROR,
            f"❌ Failed structured output for [{cost_label}] after "
            f"{max_retries} attempts × {len(ORDERED_METHODS)} methods.",
        )
        if return_raw:
            return None, None
        return None

    async def _ainvoke_plain(
        self,
        llm: BaseChatModel,
        chat_template: ChatPromptTemplate,
        variables: dict,
        model: str,
        cost_label: Optional[str],
    ):
        chain = chat_template | llm
        start = datetime.now()
        response = await chain.ainvoke(variables)
        elapsed_s = (datetime.now() - start).total_seconds()
        logger().logp(
            DEBUG, f"⏱️ LLM call for [{cost_label}] took {elapsed_s:.2f}s.",
        )
        thinking = self._extract_thinking(response)
        if thinking:
            logger().logp(INFO, f"💭 [{cost_label}] Thinking:\n{thinking}")
        usage = dict(response.usage_metadata) if response.usage_metadata else {}
        self._record_cost(model, {model: usage}, cost_label)
        tm = get_turn_metrics()
        if tm is not None:
            tm.record(cost_label or "unknown", elapsed_s, usage)
        return self._normalize_content(response.content)
