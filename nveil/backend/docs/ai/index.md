# AI Service

**Port 8100** — LLM-powered chat processing and visualization generation.

The AI service receives user messages, classifies intent, generates
Choregraph data transformations and VisuSpec visualization XML through
LangGraph workflows, and finalises the result with ASP constraint solving via
the DIVE library.

The same graph powers both the community web flow and the public SDK — only
the entry point and a single `is_api` flag differ.

## Entry point

`ai_service/ai_server.py` — FastAPI application with lifespan setup
(`RouterLLMManager`, LangGraph PostgreSQL checkpointer, state database,
shared HTTP client).

## Modules

- [Routes](routes.md) — HTTP endpoints
- [LangGraph Workflows](workflows.md) — state machine + node catalogue
- [LLM Manager](llm-manager.md) — provider abstraction
- [Prompts](prompts.md) — Langfuse + yaml-fallback prompt system

## Stack

| Component | Technology |
|-----------|------------|
| LLM providers | `google_genai`, `openai`, `anthropic`, `mistralai`, `ollama`, `llamacpp` — selected per request via SDK headers or `LLM_PROVIDER` env |
| Orchestration | LangGraph state machines, PostgreSQL checkpointer |
| Constraint solving | Clingo ASP via DIVE (`dive.asp.ASPSolver`) |
| Prompts | Langfuse (opt-in, self-hosted) with `prompt_templates.yaml` fallback |
| Tracing | Langfuse (opt-in) — see the [Observability](../../ai_service/README.md#observability) section of the main README |
| State persistence | PostgreSQL (LangGraph checkpoints + `TurnMetrics` cost records) |

For the full architecture, retry budgets, provider plug-in instructions and
the Langfuse tracing setup, see [the main AI service README](../../ai_service/README.md).
