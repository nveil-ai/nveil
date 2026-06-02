# Deployment

## Local development

### Docker Compose

```bash
# Start all services (postgres, server, ai, file). They live under the "core"
# profile, which the setup wizard sets as the COMPOSE_PROFILES default in .env —
# so a bare `up` brings up the core stack (use --profile core to be explicit).
docker compose up -d

# Optional LLM tracing (Langfuse) runs as a separate project from the same
# file (its explicit --profile tracing overrides the COMPOSE_PROFILES default):
docker compose -p langfuse --profile tracing up -d
```

Services available at:

- Server: `https://localhost:8000`
- AI: `https://localhost:8100`
- File: `https://localhost:8200`
- Viz: `https://localhost:1024` (cmd) / `https://localhost:1025` (viewer)

In community mode, viz runs as a static service. With `nveil-cloud` installed, viz containers are spawned dynamically by the pool manager via Docker socket.

### Without Docker

```bash
# Install dependencies
pip install -e dive[asp,builder]
pip install -e choregraph
pip install -r deploy/docker/server/requirements.txt

# Run database migrations
make -C nveil upgrade_db

# Start services
make -C nveil
```

## Staging / Production (K8s)

### Namespaces

| Namespace | Services |
|-----------|----------|
| `server` | server-service |
| `ai` | ai-service |
| `file` | file-service |
| `viz-service` | Viz pods (dynamic) |

### Deploy

```bash
# Full deploy (Kustomize apply)
make release-staging

# Rolling image update only
make rollout-staging

# Single service rollout
make rollout-staging-server
make rollout-staging-ai
make rollout-staging-file
```

### Infrastructure

Terraform in `deploy/terraform/` provisions:

- GKE cluster
- Cloud SQL (PostgreSQL)
- Filestore (shared workspace NFS)
- Load balancer + SSL

### Docker images

Built from repo root with service-specific Dockerfiles:

```bash
docker build -f deploy/docker/server/dockerfile -t server:latest .
docker build -f deploy/docker/ai/dockerfile -t ai:latest .
docker build -f deploy/docker/file/dockerfile -t file:latest .
docker build -f deploy/docker/visualization/dockerfile -t viz:latest .
```

Base image: `python:3.12-slim-trixie` (Debian 13).

### Entrypoints

K8s containers use `deploy/docker/{service}/entrypoint.sh` which:

1. Generates `.env` from environment variables
2. Hardcodes `GCP=1`, `ALGORITHM=HS512`
3. Starts uvicorn with SSL

`load_dotenv(override=False)` ensures K8s manifest env vars take precedence.
