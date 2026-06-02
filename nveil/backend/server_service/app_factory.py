# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""App factory — creates a FastAPI application with all routes mounted.

Usage:
    # Production (server.py)
    app = create_app(lifespan=production_lifespan)

    # Tests (conftest.py)
    app = create_app()  # no lifespan, no side effects
    app.dependency_overrides[get_db] = ...
"""

import os
import sys
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from starlette.middleware.gzip import GZipMiddleware

# Ensure server_service directory is first on sys.path so that
# `from routes.*` always resolves to server_service/routes/, even
# when file_service is also on the path.
_this_dir = os.path.dirname(os.path.abspath(__file__))
if sys.path[0] != _this_dir:
    if _this_dir in sys.path:
        sys.path.remove(_this_dir)
    sys.path.insert(0, _this_dir)

from middleware.precompressed import PreCompressedStaticMiddleware
from middleware.security_headers import SecurityHeadersMiddleware
from utils import get_secret

_IS_PRODUCTION = get_secret("GCP") == "1"


def create_app(lifespan=None) -> FastAPI:
    """Build and return the FastAPI application with all routes and middleware.

    Args:
        lifespan: Optional async context manager for startup/shutdown.
                  Pass None for tests (no DB init, no pool, no httpx client).
    """
    app = FastAPI(
        lifespan=lifespan,
        docs_url=None if _IS_PRODUCTION else "/docs",
        redoc_url=None if _IS_PRODUCTION else "/redoc",
        openapi_url=None if _IS_PRODUCTION else "/openapi.json",
    )

    # ── Middleware (order matters: last added = first executed) ────────
    frontend_dir = os.path.join(
        os.path.dirname(__file__), "..", "..", "frontend", "dist"
    )

    # SecurityHeadersMiddleware must be added first (innermost) so it processes
    # responses BEFORE GZipMiddleware compresses them. If it ran after GZip it
    # would receive a binary blob and the nonce regex would find no <script> tags.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=500)
    app.add_middleware(
        PreCompressedStaticMiddleware,
        frontend_dir=frontend_dir,
    )

    # COOP
    from starlette.middleware.base import BaseHTTPMiddleware

    class COOPMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            response = await call_next(request)
            response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
            return response

    app.add_middleware(COOPMiddleware)

    # CORS
    from fastapi.middleware.cors import CORSMiddleware

    origins = [
        "https://localhost:8000",
        "https://app.nveil.com",
        "https://www.app.nveil.com",
        "https://34.8.13.210",
        "https://nveil.com",
        "https://www.nveil.com",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Auth routers ──────────────────────────────────────────────────
    from user_management.authentification import auth_router

    app.include_router(auth_router, prefix="/server/auth", tags=["authentification"])

    try:
        from user_management.oauth_provider import router as oauth_router
        app.include_router(oauth_router, prefix="/oauth", tags=["oauth"])
    except ImportError:
        pass

    # Plugin routes (Google auth, etc.)
    try:
        from nveilplugin.oauth import google_auth_router
        app.include_router(google_auth_router, prefix="/server/auth", tags=["authentification"])
    except ImportError:
        pass

    # ── Route modules ─────────────────────────────────────────────────
    from routes.api_keys import router as api_keys_router
    from routes.api_specifications import router as api_specifications_router
    from routes.chat import router as chat_router
    from routes.dashboard import router as dashboard_router
    from routes.data import router as data_router
    from routes.files import router as files_router
    from routes.notifications import router as notifications_router
    from routes.rooms import router as rooms_router
    from routes.settings import router as settings_router
    from routes.viz_proxy import router as viz_proxy_router

    app.include_router(notifications_router)
    app.include_router(files_router)
    app.include_router(chat_router)
    app.include_router(rooms_router)
    app.include_router(settings_router)
    app.include_router(dashboard_router)
    app.include_router(data_router)
    # Public API routes must be mounted BEFORE viz_proxy_router because
    # viz_proxy has a catch-all /api/{path:path} for Kedro Viz.
    app.include_router(api_keys_router, prefix="/api/v1", tags=["api"])
    app.include_router(api_specifications_router, prefix="/api/v1", tags=["api"])
    app.include_router(viz_proxy_router)

    try:
        from nveilplugin.billing import stripe_router
        app.include_router(stripe_router, prefix="/server/license", tags=["license"])
    except ImportError:
        pass

    # Debug routes — only mounted when TEST=1 to avoid leaking pool internals.
    if get_secret("TEST") == "1":
        from routes.debug import router as debug_router
        app.include_router(debug_router, tags=["debug"])

    # ── Health check ──────────────────────────────────────────────────
    @app.get("/health")
    async def health_check():
        return {"status": "ok"}

    return app
