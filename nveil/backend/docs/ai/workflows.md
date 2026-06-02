# LangGraph Workflows

The AI service runs a single LangGraph state machine — `UserRequest`
(`ai_service/llm_processing/graphs/workflow_request.py`) — compiled with a
PostgreSQL `AsyncPostgresSaver` checkpointer. The same graph powers both the
web flow and the public SDK; only the entry point and a single `is_api` flag
differ.

For the canonical (and always-up-to-date) mermaid diagram and node table,
see [the main AI service README](../../ai_service/README.md#langgraph-architecture).

You can dump the live topology from inside the running container:

```bash
docker compose exec ai python3 /scripts/dump_ai_graph.py > ai-graph.mmd
```

## State schema

State lives in `WorkflowState` (`workflow_state.py`) — a TypedDict divided
into four buckets:

| Key | Role |
|-----|------|
| `input` | Immutable request payload (user message, ids, language, cookies, `is_api`, …). |
| `processing` | Intermediate values written by nodes (`list_steps`, ASP facts, XML output, feedback material, retry counters, error markers, …). |
| `output` | Final response to the client (`text`, `suggestions`, optional `selection_prompt`). |
| `turn_metrics` | Token counts, latency and cost per LLM call (see `turn_metrics.py`). |

## Human-in-the-loop interrupts

Two places call `langgraph.types.interrupt()` to pause the graph and wait for
a client reply:

| Node | When | Resume payload |
|------|------|----------------|
| `transformation_clarification_gate` | LLM returned `early_exit=true` (and `consecutive_clarifications` cap not hit) | The user's reply text |
| `trigger_choregraph_run_node` | `is_api=True` — the SDK runs Choregraph locally | `{"reason": "sdk_processing_complete"}` |

Interrupts are bypassed for the SDK's clarification path (single-shot) and
when the consecutive cap (2) has been reached.

## Retry budgets

There are three independent retry budgets, listed with their caps in the
[Retry strategy](../../ai_service/README.md#retry-strategy) section of the
main README. The TL;DR:

| Source | Cap | Where |
|--------|-----|-------|
| Structured output (method × attempt) | 3 × 2 | `LangChainLLMManager._ainvoke_structured` |
| Viz XML validation | 3 | `should_retry` |
| Planning / choregraph | 3 | `MAX_PLANNING_RETRIES` |
| Consecutive clarifications | 2 | `consecutive_clarifications` |
| ASP solving timeout | 60 s | `asp_solving_node` |
| Choregraph HTTP timeout | 120 s | `trigger_choregraph_run_node` |
