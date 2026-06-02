# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Gemini-specific manager — adds context-cache support on top of the
generic LangChain manager.

One instance per Google API key (see RouterLLMManager). The cache state
(`caches`, `cache_resource_names`, `cached_prompts`, `cached_models`) is
keyed by NVEIL `cache_name` and is scoped to the API key, since Google
context caches are per-account.

The cache code preserves the behavior of the previous monolithic
`GeminiManager`: hash-based idempotent registration, oldest-eviction with
a max of 5 caches per prefix, automatic recreation on PermissionDenied
(403) or NotFound (404).
"""

from __future__ import annotations

import hashlib
from typing import Any, ClassVar, Optional

from google import genai
from google.genai import errors, types
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate
from logger import DEBUG, ERROR, INFO, SUCCESS, WARNING, logger

from shared.llm_config import LLMConfig

from .generic import LangChainLLMManager


class GeminiLLMManager(LangChainLLMManager):
    """Gemini Google GenAI manager with context-cache."""

    supports_context_cache: ClassVar[bool] = True
    supports_implicit_cache: ClassVar[bool] = True

    DEFAULT_CACHE_NAME: ClassVar[str] = "xml_generation"

    # Cache settings — applied when `for_config` instantiates a new
    # GeminiLLMManager. Override at startup if needed:
    #   GeminiLLMManager.USE_CACHE = False
    USE_CACHE: ClassVar[bool] = True
    TTL: ClassVar[str] = "3600s"

    # Per-api-key instance pool. Cache state (registered prompts,
    # CachedContent resources) is scoped to a Google account, so each
    # API key needs its own manager.
    _pool: ClassVar[dict[str, "GeminiLLMManager"]] = {}

    @classmethod
    def for_config(cls, config: LLMConfig) -> "GeminiLLMManager":
        cached = cls._pool.get(config.api_key)
        if cached is None:
            cached = cls(
                api_key=config.api_key,
                use_cache=cls.USE_CACHE,
                ttl=cls.TTL,
            )
            cls._pool[config.api_key] = cached
        return cached

    # Gemini call pricing (USD per 1M tokens). Used by `_record_cost` —
    # logged for observability only.
    PRICING: ClassVar[dict[str, dict[str, float]]] = {
        "gemini-2.5-pro": {
            "ppm_input_tokens": 1.25,
            "ppm_output_tokens": 10.0,
            "ppm_cached_content_tokens": 0.125,
        },
        "gemini-2.5-flash": {
            "ppm_input_tokens": 0.3,
            "ppm_output_tokens": 2.5,
            "ppm_cached_content_tokens": 0.03,
        },
        "gemini-2.5-flash-lite": {
            "ppm_input_tokens": 0.1,
            "ppm_output_tokens": 0.4,
            "ppm_cached_content_tokens": 0.01,
        },
        "gemini-3-flash-preview": {
            "ppm_input_tokens": 0.5,
            "ppm_output_tokens": 3,
            "ppm_cached_content_tokens": 0.05,
        },
    }

    def __init__(
        self,
        api_key: str,
        use_cache: bool = True,
        ttl: str = "3600s",
    ):
        super().__init__()
        if not api_key:
            raise ValueError("GeminiLLMManager requires a non-empty api_key.")
        self.api_key = api_key
        self.use_cache = use_cache
        self.ttl = ttl

        self.caches: dict[str, types.CachedContent] = {}
        self.cache_resource_names: dict[str, str] = {}
        self.cached_prompts: dict[str, str] = {}
        self.cached_models: dict[str, Optional[str]] = {}

        self.client = genai.Client(api_key=api_key)
        logger().logp(SUCCESS, "✅ Gemini client initialized.")
        if not self.use_cache:
            logger().logp(INFO, "Cache disabled.")

    # ------------------------------------------------------------------
    # Cache management — straight port from the legacy GeminiManager.
    # ------------------------------------------------------------------

    def _evict_oldest_cache(self, prefix: str, max_caches: int = 5) -> None:
        """Evict the oldest matching cache when the per-prefix limit is hit."""
        try:
            all_caches = list(self.client.caches.list())
            matching = [
                c for c in all_caches
                if c.display_name == prefix or c.display_name.startswith(f"{prefix}_")
            ]
            if not matching or len(matching) < max_caches:
                return

            def _created_key(c):
                created = getattr(c, "create_time", None) or getattr(c, "createTime", None)
                return created if created else getattr(c, "name", "")

            oldest = sorted(matching, key=_created_key)[0]
            try:
                self.client.caches.delete(name=oldest.name)
                logger().logp(
                    INFO,
                    f"Evicted oldest cache for prefix '{prefix}': "
                    f"{oldest.display_name} ({oldest.name})",
                )
            except Exception as e:
                logger().logp(
                    WARNING,
                    f"Failed to delete oldest cache "
                    f"{getattr(oldest, 'display_name', str(oldest))}: {e}",
                )
        except Exception as e:
            logger().logp(INFO, f"Cache eviction skipped for prefix '{prefix}': {e}")

    def register_or_refresh_cache(
        self,
        cache_name: str,
        prompt_content: str,
        model: Optional[str] = None,
    ) -> Optional[str]:
        """Idempotent: only hits the cache API when prompt content changed."""
        stored = self.cached_prompts.get(cache_name)
        if stored == prompt_content:
            return self.cache_resource_names.get(cache_name)
        return self.register_cache(cache_name, prompt_content, model=model)

    def register_cache(
        self,
        cache_name: str,
        prompt_content: str,
        model: Optional[str] = None,
    ) -> Optional[str]:
        """Register or reuse a Gemini context cache for `prompt_content`."""
        if not self.use_cache:
            logger().logp(
                INFO, f"Cache disabled, skipping registration for '{cache_name}'.",
            )
            self.cached_prompts[cache_name] = prompt_content
            self.cached_models[cache_name] = model
            return None

        prompt_hash = hashlib.sha256(prompt_content.encode("utf-8")).hexdigest()[:8]
        cache_prefix = f"cache_{cache_name}"
        display_name = f"{cache_prefix}_{prompt_hash}"

        self.cached_prompts[cache_name] = prompt_content
        self.cached_models[cache_name] = model

        logger().logp(
            INFO,
            f"[register_cache] '{cache_name}': prompt_hash={prompt_hash}, "
            f"expected display_name='{display_name}'",
        )

        # Reuse existing cache if hash matches
        found_cache = None
        try:
            for existing in self.client.caches.list():
                if existing.display_name == display_name:
                    found_cache = existing
                    break
        except Exception as e:
            logger().logp(INFO, f"Error listing caches for '{cache_name}': {e}")

        if found_cache:
            self.caches[cache_name] = found_cache
            self.cache_resource_names[cache_name] = found_cache.name
            logger().logp(
                SUCCESS,
                f"🔄 Cache reused for '{cache_name}' (ID: {found_cache.name}, "
                f"display='{found_cache.display_name}')",
            )
            return found_cache.name

        try:
            self._evict_oldest_cache(cache_prefix)
        except Exception as e:
            logger().logp(
                INFO, f"Eviction pre-check failed for '{cache_name}' (ignored): {e}",
            )

        if not model:
            raise ValueError(
                f"register_cache for '{cache_name}' requires a non-empty model."
            )
        try:
            cached_content = types.Content(
                role="user", parts=[types.Part(text=prompt_content)],
            )
            new_cache = self.client.caches.create(
                model=model,
                config=types.CreateCachedContentConfig(
                    display_name=display_name,
                    contents=[cached_content],
                    ttl=self.ttl,
                ),
            )
            self.caches[cache_name] = new_cache
            self.cache_resource_names[cache_name] = new_cache.name
            logger().logp(
                SUCCESS,
                f"✅ Cache created for '{cache_name}' (ID: {new_cache.name})",
            )
            return new_cache.name
        except errors.APIError as e:
            if e.code == 409:  # AlreadyExists
                logger().logp(
                    INFO,
                    f"Cache already exists for '{cache_name}': {e}. "
                    f"Fetching by exact display_name='{display_name}'...",
                )
                try:
                    for existing in self.client.caches.list():
                        if existing.display_name == display_name:
                            self.caches[cache_name] = existing
                            self.cache_resource_names[cache_name] = existing.name
                            logger().logp(
                                SUCCESS,
                                f"🔄 Cache retrieved for '{cache_name}' "
                                f"(ID: {existing.name})",
                            )
                            return existing.name
                    logger().logp(
                        WARNING,
                        f"⚠️ 409 received but no cache found with exact "
                        f"display_name='{display_name}' for '{cache_name}'.",
                    )
                except Exception as retrieve_e:
                    logger().logp(
                        INFO,
                        f"❌ Failed retrieving cache for '{cache_name}': {retrieve_e}",
                    )
            else:
                logger().logp(INFO, f"❌ API error creating cache for '{cache_name}': {e}")
        except Exception as e:
            logger().logp(INFO, f"❌ Error creating cache for '{cache_name}': {e}")

        return None

    def _validate_cache(
        self, resource_name: str, label: str, recreate_fn,
    ) -> bool:
        """Check that a cache resource exists; recreate via callback otherwise."""
        try:
            still_there = any(
                c.name == resource_name for c in self.client.caches.list()
            )
            if not still_there:
                logger().logp(
                    WARNING,
                    f"CachedContent disappeared for '{label}' "
                    f"({resource_name}). Recreating.",
                )
                return recreate_fn()
            return True
        except errors.APIError as e:
            if e.code == 403:
                logger().logp(
                    WARNING,
                    f"PermissionDenied during cache validation for '{label}': "
                    f"{e}. Recreating.",
                )
                return recreate_fn()
            logger().logp(
                INFO,
                f"Cache validation ignored for '{label}' (API error): {e}",
            )
            return True
        except Exception as e:
            logger().logp(
                INFO,
                f"Cache validation ignored for '{label}' (list unavailable): {e}",
            )
            return True

    def _ensure_named_cache_valid(self, cache_name: str) -> bool:
        if cache_name not in self.cache_resource_names:
            return False

        def _recreate() -> bool:
            if cache_name in self.cached_prompts:
                return self.register_cache(
                    cache_name,
                    self.cached_prompts[cache_name],
                    model=self.cached_models.get(cache_name),
                ) is not None
            return False

        return self._validate_cache(
            self.cache_resource_names[cache_name], cache_name, _recreate,
        )

    def get_registered_caches(self) -> list[str]:
        return list(self.cache_resource_names.keys())

    def clear_cache(self, cache_name: Optional[str] = None) -> None:
        """Delete a specific named cache, or all of them when cache_name is None."""
        if not self.use_cache:
            logger().logp(INFO, "Cache is disabled, nothing to clear.")
            return

        if cache_name is None:
            logger().logp(INFO, "🗑️ Clearing ALL registered caches...")
            for name in list(self.cache_resource_names.keys()):
                self.clear_cache(cache_name=name)
            logger().logp(SUCCESS, "✅ All caches cleared.")
            return

        if cache_name not in self.cache_resource_names:
            logger().logp(
                WARNING, f"⚠️ Attempted to clear unknown cache '{cache_name}'.",
            )
            return

        resource_name = self.cache_resource_names[cache_name]
        try:
            logger().logp(INFO, f"Deleting cache '{cache_name}' ({resource_name})...")
            self.client.caches.delete(name=resource_name)
            logger().logp(
                SUCCESS, f"✅ Cache '{cache_name}' deleted from Google Cloud.",
            )
        except errors.APIError as e:
            if e.code == 404:
                logger().logp(
                    WARNING,
                    f"Cache '{cache_name}' ({resource_name}) was not found "
                    f"on server (already deleted?). Cleaning local state.",
                )
            else:
                logger().logp(
                    ERROR, f"❌ API error deleting cache '{cache_name}': {e}",
                )
        except Exception as e:
            logger().logp(ERROR, f"❌ Error deleting cache '{cache_name}': {e}")

        self.caches.pop(cache_name, None)
        self.cache_resource_names.pop(cache_name, None)

    # ------------------------------------------------------------------
    # Cache application during ainvoke (overrides the generic hook).
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_system_from_template(
        chat_template: ChatPromptTemplate,
    ) -> ChatPromptTemplate:
        """Strip the system message from a template — used when its content
        is already in a Gemini context cache to avoid double-billing."""
        remaining = [
            m for m in chat_template.messages
            if not isinstance(m, SystemMessagePromptTemplate)
        ]
        return ChatPromptTemplate(
            messages=remaining,
            template_format=(
                chat_template.template_format
                if hasattr(chat_template, "template_format") else "jinja2"
            ),
            metadata=dict(chat_template.metadata) if chat_template.metadata else None,
        )

    def _resolve_llm_and_template(
        self,
        chat_template: ChatPromptTemplate,
        variables: dict,
        llm_config: LLMConfig,
        model: str,
        cache_name: Optional[str],
        model_kwargs: dict,
    ) -> tuple[BaseChatModel, ChatPromptTemplate]:
        # Defensive: a Gemini manager pinned to a different api_key shouldn't
        # see traffic for another key (the router should have routed it
        # elsewhere). Surface the bug loudly rather than silently pool-leaking.
        if llm_config.api_key != self.api_key:
            raise RuntimeError(
                "GeminiLLMManager received a call for a different api_key. "
                "Router pool keying is broken."
            )

        if not cache_name:
            return super()._resolve_llm_and_template(
                chat_template, variables, llm_config, model, cache_name, model_kwargs,
            )

        # Render system message from the template
        sys_msg_tmpl = next(
            (
                m for m in chat_template.messages
                if isinstance(m, SystemMessagePromptTemplate)
            ),
            None,
        )
        if sys_msg_tmpl is None:
            logger().logp(
                WARNING,
                f"cache_name='{cache_name}' requested but template has no "
                f"system message; falling back to plain chain.",
            )
            return super()._resolve_llm_and_template(
                chat_template, variables, llm_config, model, cache_name, model_kwargs,
            )

        try:
            sys_vars = {
                k: v for k, v in variables.items()
                if k in sys_msg_tmpl.input_variables
            }
            rendered_system = sys_msg_tmpl.format(**sys_vars).content
        except Exception as e:
            logger().logp(
                WARNING,
                f"Failed to render system message for cache '{cache_name}': "
                f"{e}; falling back to plain chain.",
            )
            return super()._resolve_llm_and_template(
                chat_template, variables, llm_config, model, cache_name, model_kwargs,
            )

        self.register_or_refresh_cache(cache_name, rendered_system, model=model)

        if (
            cache_name in self.cache_resource_names
            and self._ensure_named_cache_valid(cache_name)
        ):
            cached_content = self.cache_resource_names[cache_name]
            llm = self._get_chat_model(
                llm_config,
                model,
                cached_content=cached_content,
                **model_kwargs,
            )
            return llm, self._strip_system_from_template(chat_template)

        logger().logp(
            WARNING,
            f"Cache '{cache_name}' unavailable after refresh — sending system inline.",
        )
        return super()._resolve_llm_and_template(
            chat_template, variables, llm_config, model, cache_name, model_kwargs,
        )

    # ------------------------------------------------------------------
    # Cost estimation hook
    # ------------------------------------------------------------------

    def _record_cost(
        self,
        model: str,
        usage_metadata: dict,
        cost_label: Optional[str],
    ) -> None:
        try:
            self.estimate_gemini_call_cost(usage_metadata, cost_label or "unknown")
        except Exception as e:
            logger().logp(DEBUG, f"Cost estimation skipped for {model}: {e}")

    def estimate_gemini_call_cost(
        self, response_metadata: dict, calling_context: str,
    ) -> float:
        model = list(response_metadata.keys())[0]
        usage = response_metadata[model]
        if model not in self.PRICING:
            logger().logp(
                WARNING,
                f"Model '{model}' not recognized for pricing. Returning 0 "
                f"cost. Context: {calling_context}",
            )
            return 0.0

        pricing = self.PRICING[model]
        input_tokens = usage.get("input_tokens", 0)
        cached_tokens = (
            usage.get("input_token_details", {}).get("cache_read") or 0
        )
        if cached_tokens:
            input_tokens -= cached_tokens
            if input_tokens < 0:
                logger().logp(
                    ERROR,
                    f"Negative input tokens calculated ({input_tokens}). "
                    f"Setting to 0. Context: {calling_context}",
                )
                input_tokens = 0

        thinking_tokens = (
            usage.get("output_token_details", {}).get("reasoning") or 0
        )
        output_tokens = usage.get("output_tokens", 0)
        total = (
            input_tokens * pricing["ppm_input_tokens"]
            + output_tokens * pricing["ppm_output_tokens"]
            + cached_tokens * pricing["ppm_cached_content_tokens"]
        ) / 1_000_000
        logger().logp(
            DEBUG,
            f"Estimated call cost for '{calling_context}': "
            f"{total * 100:.4f} cents",
        )
        logger().logp(
            INFO,
            f"Details - Input tokens: {input_tokens}, Cached tokens: "
            f"{cached_tokens}, Output tokens: {output_tokens} "
            f"(Thinking tokens: {thinking_tokens})",
        )
        return total
