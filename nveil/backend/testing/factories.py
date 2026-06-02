# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Model factories for backend service tests.

Provides async helpers to insert test data into the DB.
Each function takes a db_session and optional overrides.
"""

from datetime import datetime, timezone
from uuid import uuid4

from database.core.security import hash_password


# ── Defaults ─────────────────────────────────────────────────────────────

_user_counter = 0


def _next_email():
    global _user_counter
    _user_counter += 1
    return f"user{_user_counter}@test.com"


DEFAULT_PASSWORD = "TestPass123!"
DEFAULT_HASHED_PASSWORD = None  # lazy — computed on first use


def _get_hashed_password():
    global DEFAULT_HASHED_PASSWORD
    if DEFAULT_HASHED_PASSWORD is None:
        DEFAULT_HASHED_PASSWORD = hash_password(DEFAULT_PASSWORD)
    return DEFAULT_HASHED_PASSWORD


# ── User ─────────────────────────────────────────────────────────────────

async def insert_user(session, **overrides):
    """Insert a User row and return it."""
    from database.models.user import User

    defaults = dict(
        id=str(uuid4()),
        name=overrides.pop("name", "Test User"),
        email=overrides.pop("email", _next_email()),
        _password=overrides.pop("password_hash", _get_hashed_password()),
        email_verified=overrides.pop("email_verified", True),
        is_guest=overrides.pop("is_guest", False),
        accept_cgu=True,
        accept_privacy=True,
    )
    defaults.update(overrides)
    user = User(**defaults)
    session.add(user)
    await session.flush()
    return user


# ── Room ─────────────────────────────────────────────────────────────────

async def insert_room(session, owner_id, **overrides):
    """Insert a Room row and return it (no filesystem ops)."""
    from database.models.room import Room

    defaults = dict(
        id=str(uuid4()),
        name=overrides.pop("name", "Test Room"),
        owner_id=owner_id,
        token=str(uuid4()),
    )
    defaults.update(overrides)
    room = Room(**defaults)
    session.add(room)
    await session.flush()
    return room


# ── RoomMember ───────────────────────────────────────────────────────────

async def insert_room_member(session, room_id, user_id, role="OWNER"):
    """Insert a RoomMember row."""
    from database.models.room import RoomMember

    member = RoomMember(
        id=str(uuid4()),
        room_id=room_id,
        user_id=user_id,
        role=role,
    )
    session.add(member)
    await session.flush()
    return member


# ── Message ─────────────────────────────────────────────────────────────

async def insert_message(session, room_id, author_id, content="Test message"):
    """Insert a Message row."""
    from database.models.message import Message

    msg = Message(
        id=str(uuid4()),
        room_id=room_id,
        author_id=author_id,
        content=content,
    )
    session.add(msg)
    await session.flush()
    return msg
