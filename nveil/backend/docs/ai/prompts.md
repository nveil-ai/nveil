# Prompts

Prompts are defined as Python classes in `ai_service/llm_processing/prompt.py`.
Each subclass of `Prompt` declares:

- `LANGFUSE_NAME` — canonical name (used both as the yaml key and the Langfuse
  prompt name).
- `prepare_vars(**kwargs)` — computes the template variables.

Call sites have a single entry point:

```python
template, variables, lf_ref = PromptSubclass().build(**context)
response = await llm_manager.ainvoke(chat_template=template, variables=variables, ...)
```

## Prompt sources

The service has two prompt stores; the lookup order is **Langfuse first,
yaml fallback**:

1. **Langfuse** — when `LANGFUSE_TRACING=1` and reachable. Each `Prompt.build()`
   calls `lf.get_prompt(LANGFUSE_NAME, label=LANGFUSE_PROMPT_LABEL, type="chat")`.
   The returned object is attached as `metadata={"langfuse_prompt": p}` on
   the `ChatPromptTemplate` so the generation is linked to that prompt
   version in the trace.
2. **`prompt_templates.yaml`** — shipped in the repo at
   `ai_service/llm_processing/prompt_templates.yaml`. Used when Langfuse is
   disabled, unreachable, or has no version at the requested label. The yaml
   is always the canonical source for community deployments.

To seed the yaml prompts into a self-hosted Langfuse so they're editable in
the UI, run once:

```bash
docker compose exec ai python /scripts/seed_langfuse_prompts.py
```

Two yaml sections are intentionally skipped because they are consumed by
Python helpers and never sent to the LLM:

- `_xml_mapping_rules`
- `question_answering`

They remain yaml-only and won't appear in the Langfuse UI.

See the [Langfuse tracing](../../ai_service/README.md#langfuse-tracing-opt-in-self-hosted)
section of the main README for the full opt-in setup.

## Round-trip: persisting UI edits back to yaml

Editing a prompt in the Langfuse UI creates a new version **in the local
Langfuse database only**. The change is not auto-synced to
`prompt_templates.yaml`, so:

- It is lost when the Langfuse volumes are dropped
  (`docker compose -p langfuse down -v`).
- It does not propagate to other deployments (which read yaml from git).
- Disabling `LANGFUSE_TRACING` makes the AI service fall back to the
  pre-edit yaml content.

To make an edit canonical, snapshot Langfuse back into the yaml via the
host-side Makefile target:

```bash
# One-time host install
pip install langfuse pyyaml

# Pull every prompt at label=production into prompt_templates.yaml
make ai-prompts-release-snapshot

# …or any other label
make ai-prompts-release-snapshot LABEL=staging
```

The script (`nveil-community/scripts/export_prompts_to_yaml.py`) preserves
the yaml-only sections and emits a stderr warning for any prompt that has no
version at the requested label. Commit the resulting diff to make the edit
part of the project.

### Label conventions

| Label | Default in | Intended use |
|-------|------------|--------------|
| `latest` | `LANGFUSE_PROMPT_LABEL` env var · `seed_langfuse_prompts.py --label` | Dev iteration. Each seed bumps the version at this label. |
| `production` | `make ai-prompts-release-snapshot LABEL=…` | Stable snapshots intended to be committed back to yaml. |

The Langfuse UI lets you re-label an existing version, which is the
intended flow: iterate on `latest`, promote a known-good version to
`production`, then run the export.

## Catalogue

Chat prompts (top-level entries in `prompt_templates.yaml`):

| `LANGFUSE_NAME` | Used by node |
|-----------------|--------------|
| `entrypoint_classification` | `entry_classif_message_type` |
| `planning_transformation_normal` | `planning_transformation_node` |
| `planning_transformation_fallback` | `planning_transformation_node` (retry path) |
| `xml_generation` | `xml_generation` (viz subgraph) |
| `keyword_classification` | `classify_user_intention` |
| `exclusion_processing` | `exclusion_processing` |
| `feedback` | `feedback_node` |
| `csv_characterization` | `/ai/characterize_csv` route |
| `sample_creation` | `/ai/preprocess_excel` route |

Shared text fragments live under `_fragments/{category}/{key}` in the yaml
and as `shared/{category}/{key}` Langfuse text prompts. They are pulled by
`Prompt.fragment(category, key)` and populate tone/action/step-hint slots in
the chat templates (e.g. `_fragments.step_actions.visualization_request`).

## Variables

Chat templates use mustache (`{{variable_name}}`) at definition time.
`Langfuse.get_langchain_prompt()` translates them to f-string syntax
(`{variable_name}`) on fetch. The yaml-fallback path uses
`BasePromptClient._get_langchain_prompt_string` to ensure parity with the
live Langfuse fetch, so JSON examples and DSL literals (`{{mark:..}}`) are
handled identically on both paths.

## Caching

The Langfuse SDK caches fetched prompts for `LANGFUSE_PROMPT_CACHE_TTL`
seconds (default 5 s when tracing is on, 60 s when off). Provider-side
context caching (Gemini) is configured per node via the `cache_name`
parameter on `llm_manager.ainvoke` and is silently ignored by providers
without context-cache support.
