# AI Routes

All routes are mounted under `/ai/` on port **8100**. The full request /
response schemas are documented at <https://localhost:8100/docs> (FastAPI
auto-generated, accept the self-signed cert).

## Chat processing

| Method | Path | Description |
|--------|------|-------------|
| POST | `/ai/process_user_message` | Main chat endpoint — runs the `UserRequest` LangGraph workflow. Web-flow oriented (uses `room_id` as thread id). |
| POST | `/ai/sdk/process` | Unified SDK endpoint, polymorphic on `session_id`. **Fresh** (no `session_id`) runs classification + planning and pauses at the choregraph interrupt (the SDK runs Choregraph locally). **Resume** (with `session_id`) finishes viz generation + ASP and returns the spec. |

## User settings

| Method | Path | Description |
|--------|------|-------------|
| GET | `/ai/user/settings` | Get the user's AI preferences (tone, additional info). |
| POST | `/ai/user/settings` | Update the user's AI preferences. |

## Data preprocessing

| Method | Path | Description |
|--------|------|-------------|
| POST | `/ai/characterize_csv` | LLM-based fallback when heuristic CSV characterization fails — detects header presence, column separator, record separator. |
| POST | `/ai/preprocess_excel` | Detect tables in an Excel sheet and write companion parquet files for each. |

## Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/ai/health` | Service health check. |

## `POST /ai/process_user_message`

Request:

```json
{
  "message": "Show revenue per region as bars",
  "user_id": "uuid",
  "room_id": "uuid",
  "owner_id": "uuid",
  "room_token": "string",
  "user_language": "en",
  "is_upload": false,
  "is_selection": false,
  "message_history": [ ... ]
}
```

Response (normal completion):

```json
{
  "text": "<html feedback>",
  "suggestions": [ {"text": "...", "type": "color_palette", "config": {...}} ],
  "selection_prompt": null
}
```

Response when the graph paused on a clarification interrupt:

```json
{
  "text": "<feedback explaining the ambiguity>",
  "suggestions": [],
  "selection_prompt": { "prompt_id": "...", "prompt": "...", "options": [...] }
}
```

## `POST /ai/sdk/process` — two-phase contract

See the *HTTP routes* section of the main
[AI service README](../../ai_service/README.md) for the full fresh-vs-resume
payload shapes and the workspace cleanup guarantees.

## LLM provider selection

The provider is server-wide and fixed at startup — chat and SDK calls cannot
pin or override it (see the [LLM manager doc](llm-manager.md#provider-config-llmconfig)).
The lifespan walks `PROVIDER_BOOT_ORDER`
(`google_genai`, `openai`, `anthropic`, `mistralai`, `ollama`, `llamacpp`) and keeps the
first one whose env-level config passes a smoke-test. There is no global NVEIL
key — operators set their own through the setup, and every request resolves to
that provider via `get_llm_config()`.
