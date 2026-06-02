# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Debug routes — only mounted when TEST=1. Never exposed in production."""

from database.core.database import db
from fastapi import APIRouter

router = APIRouter()


@router.get("/server/debug/pool")
async def db_pool_status():
    """Return live SQLAlchemy connection pool counters."""
    pool = db.engine.pool
    size = pool.size()
    checked_out = pool.checkedout()
    checked_in = pool.checkedin()
    overflow = pool.overflow()
    return {
        "raw": pool.status(),
        "size": size,
        "checked_in": checked_in,
        "checked_out": checked_out,
        "overflow": overflow,
        "max_overflow": db.max_overflow,
        "total_capacity": size + max(db.max_overflow or 0, 0),
    }
