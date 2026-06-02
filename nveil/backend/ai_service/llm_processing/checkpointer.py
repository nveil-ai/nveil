# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
from shared.secrets import get_secret
from logger import logger, DEBUG, ERROR

_checkpointer = None
_pool = None  # keep pool alive for the lifetime of the process


async def get_checkpointer():
    global _checkpointer, _pool
    if _checkpointer is None:
        db_url = get_secret("CHECKPOINT_DATABASE_URL")
        if not db_url:
            state_url = get_secret("STATE_DATABASE_URL", "")
            # psycopg (v3) needs postgresql:// without +asyncpg
            db_url = state_url.replace("+asyncpg", "")
        # autocommit=True is required because setup() runs CREATE INDEX CONCURRENTLY,
        # which cannot execute inside a transaction block.
        _pool = AsyncConnectionPool(
            db_url,
            min_size=1,
            max_size=10,
            open=False,
            kwargs={"autocommit": True},
        )
        await _pool.open()
        _checkpointer = AsyncPostgresSaver(_pool)
        await _checkpointer.setup()  # creates checkpoint tables if missing
    return _checkpointer


async def close_checkpointer():
    global _checkpointer, _pool
    _checkpointer = None
    if _pool is not None:
        await _pool.close()
        _pool = None


async def clear_thread(thread_id: str):
    """Delete all checkpoint data for a given thread.

    This is called after successful graph completion or when the user
    abandons a pending clarification by sending a different message.
    """
    if _checkpointer is None:
        return
    # Borrow a connection from the pool to purge checkpoint rows.
    # AsyncPostgresSaver stores data in checkpoints, checkpoint_blobs, checkpoint_writes.
    try:
        async with _pool.connection() as conn:
            await conn.execute(
                "DELETE FROM checkpoint_writes WHERE thread_id = %s", (thread_id,)
            )
            await conn.execute(
                "DELETE FROM checkpoint_blobs WHERE thread_id = %s", (thread_id,)
            )
            await conn.execute(
                "DELETE FROM checkpoints WHERE thread_id = %s", (thread_id,)
            )
        logger().logp(DEBUG, f"Cleared checkpoint for thread {thread_id}")
    except Exception as e:
        logger().logp(ERROR, f"Failed to clear checkpoint for thread {thread_id}: {e}")
