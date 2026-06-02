# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Add ON DELETE CASCADE to user_files.owner_id → users.id.

Migration 0004 added cascade-delete FKs for most tables but missed
`user_files`. The UserFile model (user_file.py) declares
``ondelete="CASCADE"`` on its owner_id FK, but that declaration only
takes effect when a migration applies it. Result: deleting a user
fails with FK violation on `fk_user_files_owner_id_users` because the
DB-level constraint is still the plain, no-cascade version.

This migration brings the DB in line with the model.

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from utils import get_secret

revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = get_secret("DATABASE_SCHEMA", "nveilseption")


def _replace_fk(table, column, ref_table, ref_column="id",
                on_delete="CASCADE", old_constraint=None):
    """Drop an existing FK and recreate it with ON DELETE behaviour.

    Copy of the helper from 0004 — auto-discovers constraint name so we
    work across DBs with auto-named or explicit constraint names.
    """
    fk_name = old_constraint or f"fk_{table}_{column}_{ref_table}"
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
    _replace_fk("user_files", "owner_id", "users")


def downgrade() -> None:
    op.execute(
        f"ALTER TABLE {SCHEMA}.user_files "
        f"DROP CONSTRAINT IF EXISTS fk_user_files_owner_id_users"
    )
    op.execute(
        f"ALTER TABLE {SCHEMA}.user_files "
        f"ADD CONSTRAINT fk_user_files_owner_id_users "
        f"FOREIGN KEY (owner_id) REFERENCES {SCHEMA}.users(id)"
    )
