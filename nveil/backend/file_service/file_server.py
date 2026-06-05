# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""NVEIL File Service -- owns all file management operations.

Port 8200. Auth via mTLS + X-Owner-Id header from server proxy.
Shared PostgreSQL (same DB, same schema as server_service).
"""

import os
import sys
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.schema import CreateSchema

backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from logger import ERROR, INFO, SUCCESS, logger
from shared.secrets import get_secret

logger(service="FILE", service_id="MAIN")

DATABASE_URL = get_secret("DATABASE_URL")
DB_SCHEMA = get_secret("DATABASE_SCHEMA")

# Long-lived async HTTP client for outbound calls to trusted internal services
# (ai-service) and external third-party URLs. Lives for the process lifetime so
# connections stay pooled — avoids a TLS handshake on every file upload/URL fetch.
httpx_client: httpx.AsyncClient = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    from db.core.database import db

    if DATABASE_URL:
        db.initialize(url=DATABASE_URL, echo=False)
        try:
            async with db.engine.begin() as conn:
                await conn.execute(CreateSchema(DB_SCHEMA, if_not_exists=True))
                # Tables are managed by Alembic (server_service). Just verify connectivity.
                await conn.execute(text("SELECT 1"))
            logger().logp(SUCCESS, "Database initialized")
        except Exception as e:
            logger().logp(ERROR, f"Database initialization failed: {e}")
    else:
        logger().logp(ERROR, "DATABASE_URL not set")

    global httpx_client
    limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
    httpx_client = httpx.AsyncClient(limits=limits, verify=True, follow_redirects=True)

    from routes.data import set_httpx_client
    set_httpx_client(httpx_client)

    # Route choregraph's CSV LLM characterization step to the ai_service
    # (mirrors Excel tidying via /ai/preprocess_excel) so provider credentials
    # stay confined to the ai_service and never need to live in file_service.
    from choregraph.loaders import set_csv_llm_delegate
    from routes.data import characterize_csv_via_ai
    set_csv_llm_delegate(characterize_csv_via_ai)

    logger().logp(INFO, "File Service started on port 8200")
    yield

    # SHUTDOWN
    from db.core.dependencies import cleanup_service_cache

    cleanup_service_cache()
    if httpx_client is not None:
        await httpx_client.aclose()
    await db.close()
    logger().logp(INFO, "File Service shutdown")


# ── Create the app via factory, with production lifespan ──────────────
from app_factory import create_app

app = create_app(lifespan=lifespan)
