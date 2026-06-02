# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Provider-routing LLM manager.

A single instance is held by the FastAPI app and injected into the
LangGraph constructor. Each call dispatches by `llm_config.provider`
to the concrete manager class registered in `PROVIDER_OVERRIDES`. The
instantiation/pooling strategy lives on the concrete class
(`for_config`), not here — the router only knows which class handles
which provider.
"""

from __future__ import annotations

from typing import Any, ClassVar, Optional, Type

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from shared.llm_config import LLMConfig

from .base import LLMManager
from .gemini import GeminiLLMManager
from .generic import LangChainLLMManager


class RouterLLMManager(LLMManager):
    """Routes calls to the right concrete manager by provider.

    Providers not listed in `PROVIDER_OVERRIDES` fall back to
    `LangChainLLMManager` — that's the common case, the only override
    today is Gemini (which needs its own per-api-key instance for cache
    state).
    """

    PROVIDER_OVERRIDES: ClassVar[dict[str, Type[LangChainLLMManager]]] = {
        "google_genai": GeminiLLMManager,
    }

    def _resolve(self, llm_config: LLMConfig) -> LLMManager:
        cls = self.PROVIDER_OVERRIDES.get(llm_config.provider, LangChainLLMManager)
        return cls.for_config(llm_config)

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
        return await self._resolve(llm_config).ainvoke(
            chat_template=chat_template,
            variables=variables,
            llm_config=llm_config,
            model=model,
            response_schema=response_schema,
            cost_label=cost_label,
            cache_name=cache_name,
            return_raw=return_raw,
            **model_kwargs,
        )
