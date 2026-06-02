# Environment Variables

All services read configuration via `shared/secrets.py` → `get_secret(key, default)`, which checks environment variables then falls back to `.env`.

## Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | — | PostgreSQL connection (server + file services) |
| `DATABASE_SCHEMA` | `public` | Schema name |
| `STATE_DATABASE_URL` | — | PostgreSQL connection (AI service state) |
| `STATE_DATABASE_SCHEMA` | `state_schema` | AI state schema name |

## Services

| Variable | Default | Description |
|----------|---------|-------------|
| `SERVER_HOST` | `localhost` | Server service bind address |
| `SERVER_PORT` | `8000` | Server service port |
| `AI_HOST` | `localhost` | AI service host |
| `AI_PORT` | `8100` | AI service port |
| `FILE_HOST` | `localhost` | File service host |
| `FILE_PORT` | `8200` | File service port |

## Filesystem

| Variable | Default | Description |
|----------|---------|-------------|
| `DIVE_PATH` | `/root/DIVE` | Workspace filesystem root |

## Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET` | — | Secret key for JWT signing |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm (`HS256` local, `HS512` K8s) |
| `REFRESH_TOKEN_EXPIRES_DAYS` | `7` | Refresh token lifetime |

## LLM

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_API_KEY` | — | Google Gemini API key |

## Email

| Variable | Default | Description |
|----------|---------|-------------|
| `SENDGRID_API_KEY` | — | SendGrid API key |
| `FROM_EMAIL` | `no-reply@app.nveil.com` | Sender address |

## OAuth2

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_CLIENT_ID` | — | Google OAuth2 client ID |
| `GOOGLE_CLIENT_SECRET` | — | Google OAuth2 client secret |
| `GITHUB_CLIENT_ID` | — | GitHub OAuth2 client ID |
| `GITHUB_CLIENT_SECRET` | — | GitHub OAuth2 client secret |

## SSL

| Variable | Default | Description |
|----------|---------|-------------|
| `SSL_KEYFILE` | — | Path to SSL private key |
| `SSL_CERTFILE` | — | Path to SSL certificate |

## Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `LOCAL` | — | Enable local development mode |
| `GCP` | — | Enable GCP mode (Cloud Logging, service discovery) |
| `TEST` | — | Enable test mode |
| `ENV` | `local` | Environment (`local`, `staging`, `production`) |
