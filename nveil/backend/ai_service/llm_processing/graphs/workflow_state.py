# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""LangGraph state container and its dict-merging reducer.

Convention
----------
The three slots of ``WorkflowState`` have well-defined roles:

* ``input`` — the request payload: everything the caller hands to the
  graph (``raw_user_input``, ``room_id``, ``message_history``, cookies,
  ``additional_info``, …). Nodes may read it, but never rewrite it.
* ``processing`` — all intermediates produced by the graph: XML output,
  dynamic ASP facts, ``feedback_material`` accumulated across nodes,
  ``list_steps``, ``user_question``, ASP/viz_build results,
  ``feedback_text``, ``color_palette_config``, ``selection_prompt``, …
  Nodes read and write freely here.
* ``output`` — ONLY the final response returned to the client
  (``state.output['response'] = {text, suggestions, selection_prompt?}``).
  Populated exclusively by ``format_feedback`` (the terminal node).
  Both the normal feedback LLM path and the ``#bypass_feedback``
  short-circuit flow through ``format_feedback`` — the bypass writes a
  canned ``feedback_text`` which the formatter wraps in HTML like any
  other response.

Any intermediate signal — even one produced by the feedback LLM — lives
in ``processing``. The terminal node is the single place that materializes
``output``.
"""

from dataclasses import dataclass, field
from typing import Annotated, Any, Dict


def merge_dicts(a, b):
    """
    Merges two dictionaries by combining values:
    - For lists: concatenates and removes duplicates (handles non-hashable items like dicts)
    - For strings: keeps the non-empty value
    - For others: keeps the value of b if not None, otherwise that of a
    """
    merged = {**(a or {})}
    
    for key, b_value in (b or {}).items():
        if key not in merged:
            # Key only in b
            merged[key] = b_value
        else:
            a_value = merged[key]
            
            # Merge strategy based on type
            if isinstance(a_value, list) and isinstance(b_value, list):
                combined = a_value + b_value
                try:
                    # Faster path for hashable items (strings, ASP facts)
                    merged[key] = list(dict.fromkeys(combined))
                except TypeError:
                    # Fallback for non-hashable items (dictionaries in history)
                    # Maintains order and removes exact duplicates
                    unique_list = []
                    for item in combined:
                        if item not in unique_list:
                            unique_list.append(item)
                    merged[key] = unique_list
            
            elif isinstance(a_value, str) and isinstance(b_value, str):
                # Keep the non-empty value (priority to b if both are filled)
                merged[key] = b_value if b_value else a_value
            
            elif isinstance(a_value, dict) and isinstance(b_value, dict):
                # Recursively merge sub-dictionaries
                merged[key] = merge_dicts(a_value, b_value)
            
            else:
                # For other types: keep b if defined, otherwise a
                if b_value is not None and b_value != "" and b_value != []:
                    merged[key] = b_value
                else:
                    merged[key] = a_value
    
    return merged

@dataclass
class WorkflowState:
    input: Annotated[Dict[str, Any], merge_dicts] = field(default_factory=dict)
    processing: Annotated[Dict[str, Any], merge_dicts] = field(default_factory=dict)
    output: Annotated[Dict[str, Any], merge_dicts] = field(default_factory=dict)
