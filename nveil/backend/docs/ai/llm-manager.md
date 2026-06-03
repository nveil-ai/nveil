# LLM Manager

The AI service is provider-agnostic. The LLM provider (model, base URL, API
key) is chosen once at startup from the operator's environment (`.env`,
written by the setup) and is used for **every** request — clients cannot
override it.

For the full provider plug-in walk-through (adding a new provider, local
models via Ollama/llama.cpp, OpenAI-compatible proxies), see the main
[AI service README](../../ai_service/README.md#plugging-in-your-own-llm).

## Layers

Code lives under `ai_service/llm_processing/managers/`.

| Class | Role |
|-------|------|
| `LLMManager` (`base.py`) | Abstract base — defines `ainvoke` / `ainvoke_structured`. |
| `LangChainLLMManager` (`generic.py`) | Default implementation. Wraps `langchain.init_chat_model` and handles structured-output retries (`json_schema` then `function_calling`, 3 attempts each). |
| `GeminiLLMManager` (`gemini.py`) | Subclass override that adds Google's context-cache support. |
| `RouterLLMManager` (`router.py`) | Singleton held by the FastAPI app. Dispatches a request to the right manager based on `llm_config.provider`. |

## Provider config (`LLMConfig`)

`shared/llm_config.LLMConfig` is the immutable dataclass carried through
LangGraph nodes via `RunnableConfig.configurable["llm_config"]`. It always
holds the server's boot-selected provider (same value for every request):

```python
LLMConfig(
    provider="anthropic",
    api_key="...",
    base_url=None,        # optional — for OpenAI-compatible proxies
    model_override=None,  # optional — overrides yaml model for every node
)
```

At startup, ai_service walks `PROVIDER_BOOT_ORDER` (`google_genai`, `openai`,
`anthropic`, `mistralai`, `ollama`, `llamacpp`) and picks the **first** provider whose
env-level config (matching `<PROVIDER>_API_KEY`, or `<PROVIDER>_BASE_URL` +
`<PROVIDER>_MODEL` for locals) passes a one-token smoke-test. That config is
the boot-time default. If no provider passes, the service refuses to start —
operators provide keys via the setup TUI, which writes them to
`docker-compose.yaml` + `.env`.

`LLMConfig.from_env_ordered()` exposes the same boot list to callers (used in
ai_service's lifespan). `LLMConfig.from_env()` returns the top-priority entry.
`ai_server.get_llm_config()` returns the boot-selected default for every
request — there is no header-based override.

## Model pool

`build_chat_model` caches `BaseChatModel` instances in a pool keyed on
`(provider, model, base_url, sha256(api_key)[:12], frozen_kwargs)` so users
stay isolated and quantized-model swaps don't reuse a stale model object.

## Token tracking

Every LLM call records token usage via `TurnMetrics` (`turn_metrics.py`):

- `input_tokens` — tokens in the prompt
- `output_tokens` — tokens generated
- `cached_tokens` — tokens served from prompt cache (Gemini only currently)
- `latency_ms` — round-trip time
- `cost_label` — human-readable label set by the node (`"XML Generation Node"`,
  `"Feedback Node"`, …)

Metrics are persisted per-turn in `turn_metrics_record` for cost analysis and
rendered as an end-of-turn table in service logs.

## Per-node config (yaml)

Per-node kwargs (model, temperature, thinking…) live in
`llm_processing/configs/<provider>.yaml` in the provider's **native** syntax —
no abstraction layer. See [the main README](../../ai_service/README.md#per-node-configuration-yaml)
for the merging rules.
