# Server Service

**Port 8000** — Core orchestration service

The server service is the main entry point for the frontend. It handles user authentication, room lifecycle, dashboard management, WebSocket events, and proxies requests to AI, File, and Viz services.

## Entry point

`server_service/server.py` — FastAPI application with WebSocket hub and AI proxy endpoints.

`server_service/app_factory.py` — Mounts all routers, middleware, and static files.

## Modules

- [Routes](routes.md) — HTTP and WebSocket endpoints
- [Database Models](models.md) — SQLAlchemy ORM models
- [Services](services.md) — Business logic layer
- [WebSocket](websocket.md) — Real-time event broadcasting
- [Room Management](rooms.md) — Viz container pool lifecycle

## Middleware stack

1. **SecurityHeadersMiddleware** — CSP, X-Frame-Options, HSTS
2. **PreCompressedStaticMiddleware** — Serve `.br`/`.gz` assets
3. **COOPMiddleware** — Cross-Origin-Opener-Policy
4. **CORSMiddleware** — Allowed origins
5. **GZipMiddleware** — Response compression (> 500 bytes)
