# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""LLM provider configuration shared across NVEIL backend services.

`LLMConfig` is the immutable per-request credential pair (provider + API key)
carried via `RunnableConfig.configurable` through LangGraph nodes. It is
intentionally minimal: model selection and provider-specific kwargs come
from per-provider yaml files (`llm_processing/configs/<provider>.yaml`)
that are written in each provider's native syntax — no abstraction layer.

`build_chat_model` instantiates a LangChain `BaseChatModel` from an
`LLMConfig` plus the kwargs already resolved from yaml.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from .secrets import get_secret


LLMProvider = Literal[
    "google_genai", "openai", "anthropic", "mistralai", "ollama", "llamacpp",
    "openai_compatible",
]


_PROVIDER_ENV_KEY: dict[str, str] = {
    "google_genai": "GOOGLE_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "mistralai": "MISTRAL_API_KEY",
    # Ollama / llama.cpp are OpenAI-compatible; reuse OPENAI_API_KEY (can be
    # any dummy value — these providers don't authenticate by default).
    "ollama": "OPENAI_API_KEY",
    "llamacpp": "OPENAI_API_KEY",
    # Generic OpenAI-compatible endpoint (OpenRouter, Nebius, Together, …).
    # Unlike ollama/llamacpp it does authenticate, and its base_url + model
    # also come from env (OPENAI_COMPAT_BASE_URL / OPENAI_COMPAT_MODEL).
    "openai_compatible": "OPENAI_COMPAT_API_KEY",
}

# Maps provider names to the LangChain model_provider string passed to
# init_chat_model. Providers not listed here use their own name directly.
_LANGCHAIN_PROVIDER: dict[str, str] = {
    "ollama": "openai",
    "llamacpp": "openai",
    "openai_compatible": "openai",
}

# Providers that run locally and don't require authentication. Used by
# server_service + ai_service to skip the api_key requirement and inject a
# sentinel for the OpenAI-compat client (which still needs a non-empty
# string). Kept as a frozenset so it's safe to share across imports.
LOCAL_PROVIDERS_WITHOUT_KEY: frozenset[str] = frozenset({"ollama", "llamacpp"})

# Sentinel string stored / sent when a local provider has no real key.
# Opaque value — only matters that it's non-empty so downstream code
# (LangChain ChatOpenAI, pool keying on api_key hash) keeps working.
LOCAL_API_KEY_SENTINEL: str = "local-provider-no-auth"

# NVEIL-frozen boot order. ai_service walks this list and uses the first
# provider that has a configured key (or endpoint+model for locals) and
# passes the smoke-test at startup. Adjust here — and only here — to
# change the global preference. Commercial providers come first, then the
# local OpenAI-compatible ones, and finally the generic OpenAI-compatible
# endpoint (custom base_url) as a catch-all. Any provider here can also be
# selected per-request through SDK X-Nveil-LLM-* headers regardless of order.
PROVIDER_BOOT_ORDER: tuple[str, ...] = (
    "google_genai", "openai", "anthropic", "mistralai", "ollama", "llamacpp",
    "openai_compatible",
)


@dataclass(frozen=True)
class LLMConfig:
    """Per-request LLM credentials. The model and provider-specific knobs
    are resolved from per-provider yaml — not stored here.

    `base_url` is optional and only relevant for OpenAI-compatible
    proxies (OpenRouter, Together AI, vLLM, Azure OpenAI, …). When set
    with `provider="openai"`, all calls hit that endpoint instead of
    `api.openai.com`. Native providers (Anthropic, Google, Mistral) on
    their own endpoints leave it as None.

    `model_override` bypasses the per-node yaml-defined model when set.
    Useful for OpenAI-compatible proxies where the yaml's default model
    name (e.g. `gpt-4o-mini`) doesn't match the user's actual endpoint
    (Ollama with `llama3.1`, OpenRouter with `anthropic/claude-3.5-sonnet`).
    Applies to ALL nodes for the request — there is no per-node override.
    """

    provider: LLMProvider
    api_key: str
    base_url: Optional[str] = None
    model_override: Optional[str] = None

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Convenience wrapper around `from_env_ordered()` returning the
        top-priority provider that has an env-level config. Raises if no
        provider is configured — callers that can tolerate that should
        use `from_env_ordered()` and handle the empty case explicitly.

        Note: this does NOT run a smoke-test (vs ai_service's boot-time
        selection which does). It only checks that env vars are set.
        """
        configs = cls.from_env_ordered()
        if not configs:
            raise ValueError(
                "No LLM provider configured. Set at least one of: "
                "GOOGLE_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, "
                "MISTRAL_API_KEY, OLLAMA_BASE_URL+MODEL, "
                "LLAMACPP_BASE_URL+MODEL, or "
                "OPENAI_COMPAT_BASE_URL+API_KEY+MODEL."
            )
        return configs[0]

    @classmethod
    def from_env_ordered(cls) -> list["LLMConfig"]:
        """Build the ordered list of provider configs from env vars.

        Walks `PROVIDER_BOOT_ORDER` and returns one `LLMConfig` per
        provider that has a usable env-level config:
          - commercial providers: matching ``<PROVIDER>_API_KEY`` is set.
          - local providers (ollama, llamacpp): both ``<PROVIDER>_BASE_URL``
            and ``<PROVIDER>_MODEL`` are set; the api_key gets the local
            sentinel since these endpoints don't authenticate.
          - generic OpenAI-compatible (``openai_compatible``): all three of
            ``OPENAI_COMPAT_BASE_URL`` / ``OPENAI_COMPAT_API_KEY`` /
            ``OPENAI_COMPAT_MODEL`` are set (OpenRouter, Nebius, Together, …).

        An empty list means the operator hasn't configured any provider —
        ai_service must refuse to start in that case (no NVEIL fallback).
        """
        configs: list[LLMConfig] = []
        for provider in PROVIDER_BOOT_ORDER:
            if provider == "openai_compatible":
                base_url = get_secret("OPENAI_COMPAT_BASE_URL")
                api_key = get_secret("OPENAI_COMPAT_API_KEY")
                model = get_secret("OPENAI_COMPAT_MODEL")
                if base_url and api_key and model:
                    configs.append(cls(
                        provider=provider,
                        api_key=api_key,
                        base_url=base_url,
                        model_override=model,
                    ))
                continue

            if provider in LOCAL_PROVIDERS_WITHOUT_KEY:
                base_url = get_secret(f"{provider.upper()}_BASE_URL")
                model = get_secret(f"{provider.upper()}_MODEL")
                if base_url and model:
                    configs.append(cls(
                        provider=provider,
                        api_key=LOCAL_API_KEY_SENTINEL,
                        base_url=base_url,
                        model_override=model,
                    ))
                continue

            env_key = _PROVIDER_ENV_KEY[provider]
            api_key = get_secret(env_key)
            if api_key:
                configs.append(cls(provider=provider, api_key=api_key))
        return configs


def build_chat_model(
    config: LLMConfig,
    *,
    model: str,
    max_retries: int = 2,
    **kwargs: Any,
) -> BaseChatModel:
    """Instantiate a LangChain `BaseChatModel` for `config`.

    `model` and `**kwargs` come from a provider-specific yaml, so they're
    already in the format expected by the underlying ChatModel constructor
    (e.g. `thinking_level="low"` for Gemini, `thinking={"type":"enabled",
    "budget_tokens":2048}` for Anthropic, `reasoning_effort="low"` for
    OpenAI).
    """
    init_kwargs: dict[str, Any] = {
        "model": config.model_override or model,
        "model_provider": _LANGCHAIN_PROVIDER.get(config.provider, config.provider),
        "api_key": config.api_key,
        "max_retries": max_retries,
        **kwargs,
    }
    if config.base_url:
        init_kwargs["base_url"] = config.base_url
    return init_chat_model(**init_kwargs)
