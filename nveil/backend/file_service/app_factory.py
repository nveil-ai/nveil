# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""App factory for file_service — creates FastAPI app with routes mounted.

Usage:
    # Production (file_server.py)
    app = create_app(lifespan=production_lifespan)

    # Tests (conftest.py)
    app = create_app()  # no lifespan, no side effects
"""

from fastapi import FastAPI


def create_app(lifespan=None) -> FastAPI:
    app = FastAPI(title="NVEIL File Service",
                  lifespan=lifespan)

    from routes.data import router as data_router
    from routes.rooms import router as rooms_router

    app.include_router(data_router)
    app.include_router(rooms_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
