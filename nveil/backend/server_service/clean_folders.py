# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Remove orphaned directories under DIVE_PATH.

Four orphan categories are detected (and reported separately):

1. **Unknown owner** — `{DIVE_PATH}/<uuid>/` whose UUID is not a user_id in DB.
2. **Empty owner dir** — the whole owner directory contains zero files. Either
   because DB says they own nothing (stale dir) or because the dir is just
   empty mkdir scaffolding that was never populated. Safe to drop — the
   workspace is recreated lazily on next session.
3. **Orphan room workspace** — `{owner}/workspaces/<uuid>/` whose UUID is not
   a room owned by that user.
4. **Orphan data file** — `{owner}/data/<uuid>/` whose UUID is not a
   user_files.file_id owned by that user.

Never touched: `_guest/`, `lost+found/`, the `_guest_system` user's owner
directory, and the top-level `api/` dir (SDK-created, purged by wipe_rooms).

Usage (via scripts/Makefile):
    make -f scripts/Makefile clean-folders-dry ENV=local|staging|prod
    make -f scripts/Makefile clean-folders     ENV=local|staging|prod
"""

import argparse
import asyncio
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Set, Tuple

from database.core.database import db
from logger import ERROR, INFO, logger
from shared.workspace import DIVE_PATH
from sqlalchemy import text
from sqlalchemy.schema import CreateSchema
from utils import get_secret

DB_SCHEMA = get_secret("DATABASE_SCHEMA")
DATABASE_URL = get_secret("DATABASE_URL")

GUEST_SYSTEM_EMAIL = "_guest_system@nveil.system"
# Top-level dir names that are never inspected as owner UUIDs.
SKIP_TOPLEVEL = {"_guest", "lost+found", "api"}


def _is_uuid(val: str) -> bool:
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, AttributeError):
        return False


def _has_any_file(p: Path) -> bool:
    """True as soon as one file is found anywhere under p (short-circuits)."""
    try:
        for _ in p.rglob("*"):
            if _.is_file():
                return True
    except OSError:
        return False
    return False


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


async def _load_db_state(session) -> Tuple[Set[str], Dict[str, str], Dict[str, Set[str]], Dict[str, Set[str]], str]:
    """Return (user_ids, user_labels, rooms_by_owner, files_by_owner, guest_system_id)."""
    users = (await session.execute(
        text(f"SELECT id, email, name FROM {DB_SCHEMA}.users")
    )).all()
    user_ids = {str(uid) for uid, _, _ in users}
    user_labels = {
        str(uid): (f"{name} <{email}>" if name else email)
        for uid, email, name in users
    }
    guest_system_id = next((str(uid) for uid, email, _ in users if email == GUEST_SYSTEM_EMAIL), "")

    rooms_by_owner: Dict[str, Set[str]] = {}
    for owner_id, room_id in (await session.execute(
        text(f"SELECT owner_id, id FROM {DB_SCHEMA}.rooms")
    )).all():
        rooms_by_owner.setdefault(str(owner_id), set()).add(str(room_id))

    # Filesystem uses user_files.file_id (NOT user_files.id) as the per-file
    # directory name — see shared.workspace.user_file_path().
    files_by_owner: Dict[str, Set[str]] = {}
    for owner_id, file_id in (await session.execute(
        text(f"SELECT owner_id, file_id FROM {DB_SCHEMA}.user_files")
    )).all():
        files_by_owner.setdefault(str(owner_id), set()).add(str(file_id))

    return user_ids, user_labels, rooms_by_owner, files_by_owner, guest_system_id


def _scan_filesystem(
    root: Path,
    user_ids: Set[str],
    rooms_by_owner: Dict[str, Set[str]],
    files_by_owner: Dict[str, Set[str]],
    guest_system_id: str,
) -> Tuple[List[Path], List[Path], List[Path], List[Path]]:
    """Return (unknown_owners, empty_owners, orphan_rooms, orphan_data_files)."""
    unknown_owners: List[Path] = []
    empty_owners: List[Path] = []
    orphan_rooms: List[Path] = []
    orphan_files: List[Path] = []

    if not root.exists():
        return unknown_owners, empty_owners, orphan_rooms, orphan_files

    protected_ids = {guest_system_id} if guest_system_id else set()

    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name in SKIP_TOPLEVEL:
            continue
        if not _is_uuid(entry.name):
            continue
        if entry.name in protected_ids:
            continue

        if entry.name not in user_ids:
            unknown_owners.append(entry)
            continue

        owner_rooms = rooms_by_owner.get(entry.name, set())
        owner_files = files_by_owner.get(entry.name, set())

        # Empty if: (a) DB says owner has nothing, or (b) the dir tree
        # holds zero files (just mkdir scaffolding). Flag the whole dir
        # and don't descend — workspaces recreate lazily on next session.
        if (not owner_rooms and not owner_files) or not _has_any_file(entry):
            empty_owners.append(entry)
            continue

        ws = entry / "workspaces"
        if ws.is_dir():
            for room_dir in sorted(ws.iterdir()):
                if not room_dir.is_dir() or not _is_uuid(room_dir.name):
                    continue
                if room_dir.name not in owner_rooms:
                    orphan_rooms.append(room_dir)

        data = entry / "data"
        if data.is_dir():
            for file_dir in sorted(data.iterdir()):
                if not file_dir.is_dir() or not _is_uuid(file_dir.name):
                    continue
                if file_dir.name not in owner_files:
                    orphan_files.append(file_dir)

    return unknown_owners, empty_owners, orphan_rooms, orphan_files


def _owner_id_from_path(p: Path, root: Path) -> str:
    """Extract the owner UUID segment from a path under DIVE_PATH."""
    try:
        rel = p.relative_to(root)
    except ValueError:
        return ""
    return rel.parts[0] if rel.parts else ""


def _report(title: str, paths: List[Path], root: Path, user_labels: Dict[str, str]) -> None:
    if not paths:
        logger().logp(INFO, f"No entries for {title}")
        return
    logger().logp(INFO, f"\n=== {title} ({len(paths)}) ===")
    for p in paths:
        try:
            n = sum(1 for _ in p.rglob("*") if _.is_file())
        except OSError:
            n = 0
        owner = _owner_id_from_path(p, root)
        label = user_labels.get(owner, "<unknown user>")
        logger().logp(INFO, f"  {p}  ({n:,} files)  [{label}]")
    logger().logp(INFO, "")


def _delete_all(paths: List[Path]) -> int:
    deleted = 0
    for p in paths:
        try:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            deleted += 1
        except Exception as e:
            logger().logp(ERROR, f"Failed to delete {p}: {e}")
    return deleted


async def cleanup(dry_run: bool) -> None:
    try:
        await _init_db()
    except Exception as e:
        logger().logp(ERROR, f"❌ Database initialization failed: {e}")
        return

    async with db.session() as session:
        user_ids, user_labels, rooms_by_owner, files_by_owner, guest_system_id = await _load_db_state(session)

    if guest_system_id:
        logger().logp(INFO, f"Preserving _guest_system user (owner_id={guest_system_id})")
    else:
        logger().logp(INFO, "WARNING: _guest_system user not found — its dir is not protected")

    root = Path(DIVE_PATH)
    logger().logp(INFO, f"Scanning {root}  |  users in DB: {len(user_ids)}")
    unknown, empty_owners, orphan_rooms, orphan_files = _scan_filesystem(
        root, user_ids, rooms_by_owner, files_by_owner, guest_system_id,
    )

    _report("UNKNOWN OWNER DIRS (no matching user row)", unknown, root, user_labels)
    _report("EMPTY OWNER DIRS (no files on disk, or nothing owned in DB)", empty_owners, root, user_labels)
    _report("ORPHAN ROOM WORKSPACES (user exists, room does not)", orphan_rooms, root, user_labels)
    _report("ORPHAN DATA FILES ({owner}/data/<file_id> not in user_files)", orphan_files, root, user_labels)

    total = len(unknown) + len(empty_owners) + len(orphan_rooms) + len(orphan_files)
    if total == 0:
        logger().logp(INFO, "No orphan folders to delete")
        await db.close()
        return

    if dry_run:
        logger().logp(INFO, f"[DRY-RUN] Would delete {total} entries. No changes made.")
        await db.close()
        return

    logger().logp(INFO, f"Delete {total} orphan entries? (yes/no)")
    if sys.stdin.readline().rstrip().lower() != "yes":
        logger().logp(INFO, "❌ Cleanup cancelled")
        await db.close()
        return

    deleted = 0
    deleted += _delete_all(unknown)
    deleted += _delete_all(empty_owners)
    deleted += _delete_all(orphan_rooms)
    deleted += _delete_all(orphan_files)
    logger().logp(INFO, f"✅ Deleted {deleted}/{total} orphan entries")

    await db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no changes")
    args = parser.parse_args()
    asyncio.run(cleanup(dry_run=args.dry_run))
