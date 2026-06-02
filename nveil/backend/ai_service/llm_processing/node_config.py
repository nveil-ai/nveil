# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Provider-aware node-level LLM config loader.

Each provider has a yaml at `llm_processing/configs/<provider>.yaml` with
the same node names but provider-native kwargs (e.g. `thinking_level` for
Gemini, `thinking={type, budget_tokens}` for Anthropic, `reasoning_effort`
for OpenAI). `get_node_config` returns a merged dict (defaults + node
overrides) ready to splat into `build_chat_model(...)`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TYPE_CHECKING

import yaml

from shared.llm_config import LLMConfig, LLMProvider

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig


_CONFIG_DIR = Path(__file__).parent / "configs"
_cache: dict[str, dict[str, Any]] = {}


def load_llm_config(provider: LLMProvider) -> dict[str, Any]:
    if provider not in _cache:
        path = _CONFIG_DIR / f"{provider}.yaml"
        with open(path) as f:
            _cache[provider] = yaml.safe_load(f) or {}
    return _cache[provider]


def _apply_overrides(merged: dict[str, Any], overrides: dict[str, Any]) -> None:
    """Layer *overrides* onto *merged* in place. A `null` value removes the key."""
    for k, v in overrides.items():
        if k == "inherits":
            continue
        if v is None:
            merged.pop(k, None)
        else:
            merged[k] = v


def get_minimal_config(provider: LLMProvider) -> dict[str, Any]:
    """Resolved config for the provider's smallest/cheapest model.

    `defaults` merged with the top-level `minimal:` block. This is the single
    source of truth for the cheap model, shared with choregraph CSV
    characterization and the setup "test connection" ping.
    """
    config = load_llm_config(provider)
    merged = dict(config.get("defaults", {}))
    _apply_overrides(merged, config.get("minimal", {}) or {})
    return merged


def get_node_config(node_name: str, provider: LLMProvider) -> dict[str, Any]:
    """Merged defaults + (optional inherited profile) + node overrides for a node.

    A `null` value in the node block removes the key from defaults (used
    e.g. to disable thinking on csv_characterization). A node may declare
    `inherits: <profile>` (e.g. `minimal`) to layer a top-level profile
    section between defaults and its own overrides.
    """
    config = load_llm_config(provider)
    merged = dict(config.get("defaults", {}))
    node = (config.get("nodes", {}) or {}).get(node_name, {}) or {}
    inherits = node.get("inherits")
    if inherits:
        _apply_overrides(merged, config.get(inherits, {}) or {})
    _apply_overrides(merged, node)
    return merged


def get_call_config(
    node_name: str, config: "RunnableConfig",
) -> tuple[LLMConfig, dict[str, Any]]:
    """Resolve `(llm_config, node_kwargs)` for a workflow node call.

    Reads the per-request `LLMConfig` from `RunnableConfig.configurable`
    (set by ai_server before invoking the graph) and looks up the
    matching provider yaml for the requested node.
    """
    configurable = (config or {}).get("configurable", {}) or {}
    llm_config = configurable.get("llm_config")
    if llm_config is None:
        raise RuntimeError(
            "RunnableConfig.configurable['llm_config'] is missing — "
            "ai_server must inject it on every graph invocation."
        )
    return llm_config, get_node_config(node_name, llm_config.provider)
