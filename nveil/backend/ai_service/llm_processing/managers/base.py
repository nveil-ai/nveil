# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Abstract LLM manager interface.

Every concrete manager exposes the same `ainvoke` contract so workflow
nodes don't care which provider is in use. Provider-specific
optimizations (Gemini's context cache) are signalled via class-level
capability flags rather than runtime branching at the call sites.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Optional, Type

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from shared.llm_config import LLMConfig


class LLMManager(ABC):
    """Provider-agnostic LLM manager.

    `ainvoke` accepts the per-request `LLMConfig`, the resolved model
    id (from the per-provider yaml), and forwards provider-native
    kwargs through `**model_kwargs`. NVEIL-level concerns (response
    schema, cost label, NVEIL cache name) are explicit kwargs.
    """

    supports_context_cache: ClassVar[bool] = False
    supports_implicit_cache: ClassVar[bool] = False

    @abstractmethod
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
        ...
