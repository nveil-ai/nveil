# LLM Tracing (Langfuse)

NVEIL ships with optional [Langfuse](https://langfuse.com) integration for
the AI service. When enabled, every LLM call made by the workflow becomes a
trace you can inspect in a local web UI — useful for debugging prompts,
measuring latency, and versioning the prompt templates yourself.

The integration is **off by default** and **fully self-hosted**: no traffic
leaves your machine, no external account is required.

## What you get

- **Tracing** — every chain run inside `ai_service` is captured as a Langfuse
  trace, including model parameters, token counts, and intermediate node
  outputs. Tags identify the request type (`visualization_request`,
  `feedback`, `upload`, …).
- **Prompt management UI** — once seeded, the prompts shipped in
  `prompt_templates.yaml` appear in the Langfuse "Prompts" tab where you can
  edit, version, and label them. The AI service picks up new versions
  through the SDK cache (5 s default TTL).

## How to enable

### 1. Configure keys

Either re-run the setup wizard and toggle **Enable LLM tracing** in the
*LLM TRACING (LANGFUSE — OPTIONAL)* section…

```bash
docker compose run --rm --build setup
```

…or set the variables directly in `.env`:

```env
LANGFUSE_TRACING=1
LANGFUSE_PUBLIC_KEY=pk-lf-<your-key>
LANGFUSE_SECRET_KEY=sk-lf-<your-key>
```

The keys are seeded into the local Langfuse project the first time it
starts, so any value you pick works (they are not real credentials — just
identifiers shared between the AI service and the Langfuse instance).

### 2. Start the tracing stack

Langfuse is defined in the **same `docker-compose.yaml`** as the app, but its
six services sit under the `tracing` profile while the app services sit under
`core`. Starting it with a **different project name** (`-p langfuse`) makes it
group separately in Docker Desktop — one file, two projects:

```bash
docker compose -p langfuse --profile tracing up -d
```

Because every service is profiled, this never pulls in the `core` app services
(and `docker compose --profile core up -d` never pulls in Langfuse). It brings
up six containers in their own `langfuse` project: `langfuse-web`,
`langfuse-worker`, plus dedicated postgres, clickhouse, redis and minio. Expect
roughly **2–3 GB of RAM** on top of the base stack.

The web UI is available at:

- URL: <http://localhost:3030>
- Login: `dev@nveil.com` / `dev-password`

### 3. (Optional) Seed the prompt catalogue

The AI service falls back to `prompt_templates.yaml` whenever a prompt isn't
found in Langfuse — so you can use tracing without seeding anything. If you
want to manage prompts through the UI, run the seed script once:

```bash
docker compose exec ai python /scripts/seed_langfuse_prompts.py
```

Each top-level chat prompt (`feedback`, `xml_generation`, …) and every
shared fragment becomes a version labelled `latest`. Re-running the script
creates new versions; previous ones are preserved.

Two yaml sections are **intentionally skipped** by the seed script because
they are consumed by Python helpers, not by the LLM:

- `_xml_mapping_rules` — string constants merged into other prompts.
- `question_answering` — helper block used by the FAQ classifier.

These live only in the yaml and never appear in the Langfuse UI.

## Editing prompts and keeping them across deployments

Once seeded, you can edit any prompt through the Langfuse UI ("Prompts" tab)
and the AI service will pick up the new version through its 5 s SDK cache.
Two things are worth knowing before you rely on that workflow:

### UI edits live only in the local Langfuse database

A prompt edited in the UI creates a new version in the Langfuse postgres /
clickhouse stores. It is **not** written back to `prompt_templates.yaml`,
which means:

- `docker compose -p langfuse down -v` (with `-v`) drops the volumes and your
  edits vanish.
- Another machine cloning the repo won't see your edits — it only sees the
  yaml.
- Disabling `LANGFUSE_TRACING` makes the AI service fall back to the yaml,
  which still reflects the pre-edit prompt.

The yaml is the **canonical, reproducible source**; Langfuse is a local
edit-and-trace store. Until you persist edits back to the yaml, they are
ephemeral.

### Persisting edits back to the yaml

There is a host-side Makefile target that pulls every prompt at a given
label out of Langfuse and writes them back to `prompt_templates.yaml`:

```bash
# One-time host install
pip install langfuse pyyaml

# Snapshot the Langfuse `production` label into the yaml (default)
make ai-prompts-release-snapshot

# …or pick another label
make ai-prompts-release-snapshot LABEL=staging
```

The target writes directly to
`nveil-community/nveil/backend/ai_service/llm_processing/prompt_templates.yaml`,
preserving the yaml-only sections listed above. Commit the resulting diff in
git — that's how an edit becomes part of the project.

Any prompt that has no version at the requested label is skipped with a
warning on stderr rather than being dropped.

### Label conventions

| Label | Where used | Purpose |
|-------|------------|---------|
| `latest` | Seed script default · `LANGFUSE_PROMPT_LABEL` default at runtime | Dev iteration — every `seed_langfuse_prompts.py` run bumps `latest`. |
| `production` | Export Makefile target default | Stable snapshots intended to be committed to the yaml. |
| any custom string | `--label …` on either script · `LANGFUSE_PROMPT_LABEL` env var | Multi-environment workflows (`staging`, feature flags, A/B). |

If you want a clean separation between "what I'm experimenting with" and
"what the next release will ship", promote a tested version in the Langfuse
UI to the `production` label, then run the export.

## Disabling tracing

Either flip the toggle in the setup wizard, or remove `LANGFUSE_TRACING`
from `.env`, then restart the AI service:

```bash
docker compose up -d ai
```

The Langfuse containers keep running until you take them down explicitly:

```bash
docker compose -p langfuse down
```

Add `-v` if you also want to drop the trace history volumes.

## Troubleshooting

- **AI service starts but no traces appear** — check that
  `LANGFUSE_TRACING` is set in `.env` and that `docker compose -p langfuse ps`
  shows `langfuse-web` healthy. Traces are flushed in 5 s batches, so wait a
  few seconds after a request.
- **Prompts not visible in the UI** — they only show up after running the
  seed script. Until then, the AI service serves prompts from the yaml
  shipped in the repo.
- **`ai` container can't reach Langfuse** — because Langfuse runs in a
  separate compose project, the `ai` container reaches it across projects via
  the host's published port: `LANGFUSE_HOST=http://host.docker.internal:3030`
  (the default in `docker-compose.yaml`). Make sure the langfuse project is up
  and port 3030 is published. Only change `LANGFUSE_HOST` if you front Langfuse
  with your own reverse proxy.
