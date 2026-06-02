# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Add ON DELETE CASCADE to all foreign key constraints.

Previously most FKs had no ondelete clause, requiring manual deletion of
child records in FK-dependency order across 8+ code locations.  With
CASCADE the database handles cleanup automatically when a parent row
(user or room) is deleted.

Also adds a proper FK constraint on refresh_tokens.user_id which was
previously just an indexed column without a foreign-key relationship.

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-07 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from utils import get_secret

revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = get_secret("DATABASE_SCHEMA", "nveilseption")


def _replace_fk(table, column, ref_table, ref_column="id",
                on_delete="CASCADE", old_constraint=None):
    """Drop an existing FK and recreate it with ON DELETE behaviour.

    If *old_constraint* is None the function discovers the constraint name
    from pg_constraint so the migration works on databases where the
    original constraint was auto-named by SQLAlchemy/PostgreSQL.

    Cleans up orphaned rows before adding the new constraint to handle
    databases where referential integrity was violated.
    """
    fk_name = old_constraint or f"fk_{table}_{column}_{ref_table}"
    # Drop by discovered name (handles both explicit and auto-generated names)
    op.execute(f"""
        DO $$
        DECLARE _name text;
        BEGIN
            SELECT con.conname INTO _name
              FROM pg_constraint con
              JOIN pg_class rel ON rel.oid = con.conrelid
              JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
              JOIN pg_attribute att ON att.attrelid = con.conrelid
                                   AND att.attnum = ANY(con.conkey)
             WHERE nsp.nspname = '{SCHEMA}'
               AND rel.relname = '{table}'
               AND att.attname = '{column}'
               AND con.contype = 'f'
             LIMIT 1;
            IF _name IS NOT NULL THEN
                EXECUTE format(
                    'ALTER TABLE {SCHEMA}.{table} DROP CONSTRAINT %I', _name
                );
            END IF;
        END $$;
    """)
    # Clean orphaned rows that would violate the new FK
    op.execute(
        f"DELETE FROM {SCHEMA}.{table} "
        f"WHERE {column} NOT IN (SELECT {ref_column} FROM {SCHEMA}.{ref_table})"
    )
    op.execute(
        f"ALTER TABLE {SCHEMA}.{table} "
        f"ADD CONSTRAINT {fk_name} "
        f"FOREIGN KEY ({column}) REFERENCES {SCHEMA}.{ref_table}({ref_column}) "
        f"ON DELETE {on_delete}"
    )


def upgrade() -> None:
    # Process leaf tables first so orphan cleanup in parent tables
    # doesn't hit FK violations from children.

    # ── Leaf tables (no children depend on these) ───────────────────
    _replace_fk("connection_logs",  "user_id",  "users")
    _replace_fk("api_keys",        "user_id",  "users")
    _replace_fk("dashboard_panels", "room_id", "rooms",
                old_constraint="fk_dashboard_panels_room_id_rooms")
    _replace_fk("messages",        "room_id",  "rooms")
    _replace_fk("messages",        "author_id", "users")
    _replace_fk("room_members",    "room_id",  "rooms")
    _replace_fk("room_members",    "user_id",  "users")
    _replace_fk("license_seats",   "license_id", "licenses")
    _replace_fk("license_seats",   "user_id",  "users")

    # ── Parent tables (safe now that children are clean) ────────────
    _replace_fk("rooms",           "owner_id", "users")
    _replace_fk("licenses",        "owner_id", "users")

    # ── refresh_tokens: add FK that didn't exist ────────────────────
    # Clean orphaned rows first (no FK existed, so stale user_ids may remain)
    op.execute(
        f"DELETE FROM {SCHEMA}.refresh_tokens "
        f"WHERE user_id NOT IN (SELECT id FROM {SCHEMA}.users)"
    )
    op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_refresh_tokens_user_id_users'
            ) THEN
                ALTER TABLE {SCHEMA}.refresh_tokens
                    ADD CONSTRAINT fk_refresh_tokens_user_id_users
                    FOREIGN KEY (user_id) REFERENCES {SCHEMA}.users(id)
                    ON DELETE CASCADE;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Revert to no-cascade FKs (drop CASCADE, re-add without ON DELETE)
    for table, column, ref_table in [
        ("connection_logs",  "user_id",    "users"),
        ("rooms",            "owner_id",   "users"),
        ("room_members",     "user_id",    "users"),
        ("room_members",     "room_id",    "rooms"),
        ("messages",         "author_id",  "users"),
        ("messages",         "room_id",    "rooms"),
        ("licenses",         "owner_id",   "users"),
        ("license_seats",    "user_id",    "users"),
        ("license_seats",    "license_id", "licenses"),
        ("api_keys",         "user_id",    "users"),
        ("dashboard_panels", "room_id",    "rooms"),
    ]:
        fk_name = f"fk_{table}_{column}_{ref_table}"
        op.execute(f"ALTER TABLE {SCHEMA}.{table} DROP CONSTRAINT IF EXISTS {fk_name}")
        op.execute(
            f"ALTER TABLE {SCHEMA}.{table} "
            f"ADD CONSTRAINT {fk_name} "
            f"FOREIGN KEY ({column}) REFERENCES {SCHEMA}.{ref_table}(id)"
        )

    # Remove the FK that was added for refresh_tokens
    op.execute(
        f"ALTER TABLE {SCHEMA}.refresh_tokens "
        f"DROP CONSTRAINT IF EXISTS fk_refresh_tokens_user_id_users"
    )
