# Architecture

The NVEIL backend follows a microservices architecture with four FastAPI services, a shared PostgreSQL database, and a centralized workspace filesystem.

- [Service Map](service-map.md) — How services communicate
- [Database Schema](database.md) — Tables, relationships, and migrations
- [Authentication](authentication.md) — JWT, refresh tokens, OAuth2, API keys
- [Workspace Filesystem](workspace.md) — File storage and workspace layout
