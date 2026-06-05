# Self-hosting NVEIL

Run the complete NVEIL platform on your own infrastructure with Docker. Your raw data stays on your machines — only its *shape* (column names, types, aggregate statistics) is ever sent to the model.

This is the **Community Edition**, free and open under the AGPL. Prefer not to manage a server? The same platform is available hosted at **[nveil.com](https://nveil.com)** (freemium).

## Requirements

- **Docker** + **Docker Compose** (Docker Desktop on macOS/Windows, or Docker Engine on Linux).
- **One LLM provider** — either a commercial API key (Gemini, OpenAI, Anthropic, or Mistral) **or** a local model (Ollama, llama.cpp, or any OpenAI-compatible endpoint).
- ~4 GB RAM free and a few GB of disk for the images.

## Quick start

Everything runs from **one Compose file** that pulls prebuilt images — nothing to build.

**1.** Download **[`docker-compose.yaml`](https://github.com/nveil-ai/nveil/raw/main/docker-compose.yaml)** into an empty folder.

**2.** Run the setup wizard and open <http://localhost:3000> to configure — it writes your `.env` (database passwords, secrets, and your LLM provider):

```bash
docker compose up setup
```

**3.** Pull the images and launch:

```bash
docker compose up -d
```

Open **https://localhost:8000** (accept the self-signed certificate warning) and start chatting with your data.

!!! tip "Pin a version"
    The Compose file defaults to a known-good release. To pin a specific one, set `NVEIL_VERSION` in your `.env`.

## Configuration

The **setup wizard** is the recommended way to configure NVEIL — it generates secure secrets for you and writes a valid `.env`. You can also edit `.env` by hand. Key settings:

| Variable | Purpose |
|---|---|
| `POSTGRES_PASSWORD`, `AI_DB_PASSWORD` | Database passwords (the wizard generates these). |
| `SECRET_KEY`, `APP_ENCRYPTION_KEY` | Auth signing key and at-rest encryption key (generated). |
| *LLM provider keys* | At least one — see below. |
| `DATA_PATH` | Where your projects/data live (default: a Docker volume). |
| `COMPOSE_PROFILES` | Set to `core` by the wizard so a bare `docker compose up` starts the stack. |

### LLM providers (bring your own model)

Set **at least one** provider in `.env`. At startup the AI service tries them in order and uses the first that responds:

**Google → OpenAI → Anthropic → Mistral → Ollama → llama.cpp → OpenAI-compatible**

- Commercial: `GOOGLE_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `MISTRAL_API_KEY`.
- Local / self-hosted: `OLLAMA_BASE_URL` + `OLLAMA_MODEL`, `LLAMACPP_BASE_URL` + `LLAMACPP_MODEL`, or `OPENAI_COMPAT_BASE_URL` + `OPENAI_COMPAT_API_KEY` + `OPENAI_COMPAT_MODEL`.

Your data never leaves your infrastructure — only metadata is sent to whichever model you configure.

## Your data & projects

Your projects live in the data volume mounted at `/root/DIVE` (controlled by `DATA_PATH`, a Docker-managed volume by default). The PostgreSQL database (accounts, files, dashboards) lives in the `postgres-data` volume. Both **persist across restarts** — `docker compose down` keeps them; only `docker compose down -v` deletes them.

## Updating

Pull the latest images and recreate the containers:

```bash
docker compose pull
docker compose up -d
```

Database migrations run automatically on startup. To move between specific releases, set `NVEIL_VERSION` in `.env` first.

## Developer setup

Want to **debug**, turn on **LLM tracing**, or **build the images yourself**? Clone the repo and use `docker-compose.dev.yml` — it builds from source with live reload and TEST mode (debug routes at `/docs`):

```bash
git clone https://github.com/nveil-ai/nveil.git
cd nveil

docker compose -f docker-compose.dev.yml up setup                       # configure → localhost:3000
docker compose -f docker-compose.dev.yml --profile core up --build -d   # build & run → localhost:8000
```

Optional LLM tracing with the bundled Langfuse (→ <http://localhost:3030>):

```bash
docker compose -f docker-compose.dev.yml --profile core --profile tracing up -d
```

## Architecture

A NVEIL deployment is a handful of services on one Docker network:

| Service | Role | Port |
|---|---|---|
| **server** | API + web UI; orchestrates visualization containers | 8000 |
| **ai** | LLM processing (chat, analysis, pipeline generation) | 8100 |
| **file** | Uploads, file processing, storage | 8200 |
| **postgres** | Database (accounts, files, dashboards, state) | 5432 |
| **viz** | 3D/scientific rendering — spawned on demand by the server | — |

TLS certificates are generated automatically on first start (unique per install). The `server` spawns visualization containers as needed from the `viz` image.

## Troubleshooting

- **Browser warns about the certificate** — expected: NVEIL generates a self-signed certificate for `localhost`. Accept it to proceed.
- **A port is already in use** (5432 / 8000 / 8100 / 8200) — stop the conflicting service, or change the published ports in your Compose file.
- **"No LLM provider" at startup** — make sure at least one provider is set in `.env` (a key, or a local endpoint **and** model).
- **Start fresh** — `docker compose down` then `docker compose up -d`. ⚠️ Add `-v` **only** if you want to wipe the database and projects.

Need help? Join the **[Discord](https://discord.gg/3KdDwzT7rt)** or open a **[GitHub Discussion](https://github.com/nveil-ai/nveil/discussions)**.
