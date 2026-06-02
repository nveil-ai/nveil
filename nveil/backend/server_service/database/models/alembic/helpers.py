# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Idempotent migration helpers for PostgreSQL.

Most DDL operations have native IF NOT EXISTS support in PostgreSQL:

    op.execute(f"ALTER TABLE {SCHEMA}.t ADD COLUMN IF NOT EXISTS col TYPE")
    op.execute(f"CREATE TABLE IF NOT EXISTS {SCHEMA}.t (...)")
    op.execute(f"CREATE INDEX IF NOT EXISTS idx ON {SCHEMA}.t(col)")
    op.execute(f"DROP TABLE/INDEX/COLUMN IF EXISTS ...")

These helpers cover the cases where PostgreSQL lacks native IF NOT EXISTS.
"""

from alembic import op


def safe_create_enum(name: str, values: list[str], schema: str):
    """Create an ENUM type if it doesn't already exist."""
    val_list = ", ".join(f"'{v}'" for v in values)
    op.execute(f"""
        DO $$ BEGIN
            CREATE TYPE {schema}.{name} AS ENUM ({val_list});
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)


def safe_add_fk(table: str, constraint_name: str, fk_sql: str, schema: str):
    """Add a foreign key constraint if it doesn't already exist.

    Example:
        safe_add_fk("orders", "fk_orders_user_id_users",
                     f"FOREIGN KEY (user_id) REFERENCES {SCHEMA}.users(id)", SCHEMA)
    """
    op.execute(f"""
        DO $$ BEGIN
            ALTER TABLE {schema}.{table} ADD CONSTRAINT {constraint_name} {fk_sql};
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)


def safe_add_unique(table: str, constraint_name: str, columns_sql: str, schema: str):
    """Add a UNIQUE constraint if it doesn't already exist.

    Example:
        safe_add_unique("users", "uq_users_email", "email", SCHEMA)
    """
    op.execute(f"""
        DO $$ BEGIN
            ALTER TABLE {schema}.{table} ADD CONSTRAINT {constraint_name} UNIQUE ({columns_sql});
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
