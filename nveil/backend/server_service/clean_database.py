# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Delete unverified users and stale guest users.

Relies on ON DELETE CASCADE (migration 0004) — deleting a user row removes
all downstream rows (rooms, messages, room_members, dashboard_panels,
room_data_refs, user_files, licenses, license_seats, refresh_tokens,
connection_logs, api_keys).

Safeguards:
    * The `_guest_system@nveil.system` account is always preserved.
    * Guests younger than GUEST_GRACE are kept (active session grace window).
    * `--dry-run` reports the row impact across every cascade target
      without deleting anything.

Usage (via scripts/Makefile):
    make -f scripts/Makefile clean-db-dry   ENV=local|staging|prod
    make -f scripts/Makefile clean-db       ENV=local|staging|prod
"""

import argparse
import asyncio
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Tuple

from database.core.database import db
from logger import ERROR, INFO, logger
from shared.workspace import DIVE_PATH
from sqlalchemy import text
from sqlalchemy.schema import CreateSchema
from utils import get_secret

DB_SCHEMA = get_secret("DATABASE_SCHEMA")
DATABASE_URL = get_secret("DATABASE_URL")

GUEST_SYSTEM_EMAIL = "_guest_system@nveil.system"
# Service / bot accounts that must never be touched by this script even though
# they don't have accept_cgu/accept_privacy set.
PROTECTED_EMAILS = {
    GUEST_SYSTEM_EMAIL,
    "bot@nveil.bob",
}
# Guests younger than this are kept (fresh sessions in progress).
GUEST_GRACE = timedelta(minutes=1)
# Verified users who haven't accepted CGU/Privacy get this long to complete
# the registration form before being considered abandoned.
INCOMPLETE_GRACE = timedelta(hours=1)

# Tables that CASCADE from users.id → reported in dry-run preview.
USER_CASCADE_TABLES = [
    "rooms", "room_members", "messages", "user_files", "room_data_refs",
    "licenses", "license_seats", "refresh_tokens", "connection_logs",
    "api_keys", "dashboard_panels",
]


def _print_table(title: str, headers: List[str], rows: List[List[str]]) -> None:
    if not rows:
        logger().logp(INFO, f"No data for {title}")
        return
    widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(str(val)))
    row_fmt = " | ".join(f"{{:<{w}}}" for w in widths)
    sep = "-+-".join("-" * w for w in widths)
    logger().logp(INFO, f"\n=== {title} ===")
    logger().logp(INFO, row_fmt.format(*headers))
    logger().logp(INFO, sep)
    for row in rows:
        logger().logp(INFO, row_fmt.format(*[str(v) for v in row]))
    logger().logp(INFO, "")


async def _init_db() -> None:
    db.initialize(url=DATABASE_URL, echo=False)
    from server_service.database.models.base import Base
    import database.models.user, database.models.room, database.models.message  # noqa: F401
    import database.models.refresh_token, database.models.license  # noqa: F401
    import database.models.license_catalog, database.models.license_seat  # noqa: F401
    import database.models.dashboard_panel, database.models.user_file  # noqa: F401
    import database.models.room_data_ref  # noqa: F401
    async with db.engine.begin() as conn:
        await conn.execute(CreateSchema(DB_SCHEMA, if_not_exists=True))
        await conn.run_sync(Base.metadata.create_all)
    logger().logp(INFO, "✅ Database tables initialized")


async def _find_targets(session) -> Tuple[List[dict], List[dict], List[dict]]:
    """Return (unverified, stale_guests, incomplete_registration). Excludes _guest_system.

    Buckets are disjoint by construction:
      * unverified              — email_verified = false
      * stale_guests            — is_guest = true, older than GUEST_GRACE
      * incomplete_registration — email_verified = true, not a guest,
                                  accept_cgu/privacy not True, older than INCOMPLETE_GRACE
    """
    now = datetime.now(timezone.utc)
    q = text(f"""
        SELECT id, email, name, created_at, is_guest, email_verified,
               accept_cgu, accept_privacy
          FROM {DB_SCHEMA}.users
         WHERE NOT (email = ANY(:protected))
           AND (
                email_verified = false
             OR (is_guest = true AND created_at < :guest_cutoff)
             OR (
                  is_guest = false
                  AND email_verified = true
                  AND (accept_cgu IS NOT TRUE OR accept_privacy IS NOT TRUE)
                  AND created_at < :incomplete_cutoff
                )
           )
    """)
    rows = (await session.execute(q, {
        "protected": list(PROTECTED_EMAILS),
        "guest_cutoff": now - GUEST_GRACE,
        "incomplete_cutoff": now - INCOMPLETE_GRACE,
    })).mappings().all()

    unverified, stale_guests, incomplete = [], [], []
    for r in rows:
        d = dict(r)
        if not r["email_verified"]:
            unverified.append(d)
        elif r["is_guest"]:
            stale_guests.append(d)
        else:
            incomplete.append(d)
    return unverified, stale_guests, incomplete


async def _cascade_preview(session, user_ids: List) -> List[List[str]]:
    """One aggregate per cascade table — no per-user N+1."""
    if not user_ids:
        return []
    rows = []
    # Rooms/messages etc. are reachable via user_id or owner_id — use a CTE.
    q = text(f"""
        WITH tgt AS (SELECT unnest(CAST(:ids AS uuid[])) AS user_id),
             tgt_rooms AS (
                SELECT id FROM {DB_SCHEMA}.rooms
                 WHERE owner_id IN (SELECT user_id FROM tgt)
             )
        SELECT 'rooms'            AS t, count(*) FROM {DB_SCHEMA}.rooms            WHERE owner_id IN (SELECT user_id FROM tgt) UNION ALL
        SELECT 'room_members',      count(*) FROM {DB_SCHEMA}.room_members         WHERE user_id  IN (SELECT user_id FROM tgt)
                                                                                    OR room_id  IN (SELECT id FROM tgt_rooms) UNION ALL
        SELECT 'messages',          count(*) FROM {DB_SCHEMA}.messages             WHERE author_id IN (SELECT user_id FROM tgt)
                                                                                    OR room_id   IN (SELECT id FROM tgt_rooms) UNION ALL
        SELECT 'dashboard_panels',  count(*) FROM {DB_SCHEMA}.dashboard_panels     WHERE room_id  IN (SELECT id FROM tgt_rooms) UNION ALL
        SELECT 'room_data_refs',    count(*) FROM {DB_SCHEMA}.room_data_refs       WHERE room_id  IN (SELECT id FROM tgt_rooms) UNION ALL
        SELECT 'user_files',        count(*) FROM {DB_SCHEMA}.user_files           WHERE owner_id IN (SELECT user_id FROM tgt) UNION ALL
        SELECT 'licenses',          count(*) FROM {DB_SCHEMA}.licenses             WHERE owner_id IN (SELECT user_id FROM tgt) UNION ALL
        SELECT 'license_seats',     count(*) FROM {DB_SCHEMA}.license_seats        WHERE user_id  IN (SELECT user_id FROM tgt) UNION ALL
        SELECT 'refresh_tokens',    count(*) FROM {DB_SCHEMA}.refresh_tokens       WHERE user_id  IN (SELECT user_id FROM tgt) UNION ALL
        SELECT 'connection_logs',   count(*) FROM {DB_SCHEMA}.connection_logs      WHERE user_id  IN (SELECT user_id FROM tgt) UNION ALL
        SELECT 'api_keys',          count(*) FROM {DB_SCHEMA}.api_keys             WHERE user_id  IN (SELECT user_id FROM tgt)
    """)
    result = await session.execute(q, {"ids": [str(u) for u in user_ids]})
    for name, n in result.all():
        rows.append([name, f"{n:,}"])
    return rows


async def cleanup(dry_run: bool) -> None:
    try:
        await _init_db()
    except Exception as e:
        logger().logp(ERROR, f"❌ Database initialization failed: {e}")
        return

    async with db.session() as session:
        unverified, stale_guests, incomplete = await _find_targets(session)
        all_users = unverified + stale_guests + incomplete

        if not all_users:
            logger().logp(INFO, "No users to delete")
            await db.close()
            return

        headers = ["ID", "Email", "Name", "Created At", "Guest", "Verified", "CGU", "Privacy"]
        def _fmt(u):
            return [
                str(u["id"])[:8], u["email"], u["name"],
                u["created_at"].strftime("%Y-%m-%d %H:%M") if u["created_at"] else "N/A",
                u["is_guest"], u["email_verified"],
                u.get("accept_cgu"), u.get("accept_privacy"),
            ]
        if unverified:
            _print_table(f"UNVERIFIED USERS ({len(unverified)})", headers, [_fmt(u) for u in unverified])
        if stale_guests:
            _print_table(
                f"STALE GUEST USERS (older than {GUEST_GRACE}, count: {len(stale_guests)})",
                headers, [_fmt(u) for u in stale_guests],
            )
        if incomplete:
            _print_table(
                f"INCOMPLETE REGISTRATION — no CGU/Privacy (older than {INCOMPLETE_GRACE}, count: {len(incomplete)})",
                headers, [_fmt(u) for u in incomplete],
            )

        user_ids = [u["id"] for u in all_users]
        cascade = await _cascade_preview(session, user_ids)
        _print_table("ROWS REMOVED BY CASCADE", ["table", "count"], cascade)

        if dry_run:
            logger().logp(INFO, "[DRY-RUN] No changes made.")
            await db.close()
            return

        logger().logp(INFO, f"Delete {len(all_users)} user(s) and cascade? (yes/no)")
        if sys.stdin.readline().rstrip().lower() != "yes":
            logger().logp(INFO, "❌ Cleanup cancelled")
            await db.close()
            return

        # Single bulk delete — CASCADE handles the rest.
        await session.execute(
            text(f"DELETE FROM {DB_SCHEMA}.users WHERE id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": [str(u) for u in user_ids]},
        )
        await session.commit()

        # Filesystem: one rmtree per owner dir covers all that user's workspaces.
        for u in all_users:
            p = Path(DIVE_PATH) / str(u["id"])
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)

        logger().logp(INFO, f"✅ Deleted {len(all_users)} user(s) and cascaded children.")

    await db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no changes")
    args = parser.parse_args()
    asyncio.run(cleanup(dry_run=args.dry_run))
