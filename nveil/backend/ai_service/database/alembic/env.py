# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

# Add ai_service dir to sys.path so we can import database.model
current_dir = os.path.dirname(os.path.abspath(__file__))
ai_service_dir = os.path.abspath(os.path.join(current_dir, "../../../"))
sys.path.append(ai_service_dir)
# Also add alembic/ dir so migration scripts can `from helpers import ...`
sys.path.append(current_dir)

# Import Base and models so autogenerate sees every table
from database.model import Base
from shared.secrets import get_secret

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use STATE_DATABASE_URL (the AI service's DB). Alembic runs synchronously, so swap
# the async asyncpg dialect for psycopg v3 (the sync counterpart already in the image).
db_url = get_secret("STATE_DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url.replace("+asyncpg", "+psycopg"))

target_metadata = Base.metadata

DB_SCHEMA = get_secret("STATE_DATABASE_SCHEMA", "state_schema")


def include_object(object, name, type_, reflected, compare_to):
    """Prevent autogenerate from dropping tables, indexes, or columns it doesn't recognise."""
    if type_ == "table" and reflected and compare_to is None:
        return False
    if type_ == "index" and reflected and compare_to is None:
        return False
    if type_ == "column" and reflected and compare_to is None:
        return False
    return True


def _purge_stale_versions(connectable):
    """Clear alembic_version rows whose revision no longer exists in the migration chain."""
    from alembic.script import ScriptDirectory
    script_dir = ScriptDirectory.from_config(config)
    known_revs = {r.revision for r in script_dir.walk_revisions()}

    if not known_revs:
        return

    schema = DB_SCHEMA or "state_schema"
    placeholders = ", ".join(f"'{r}'" for r in known_revs)

    with connectable.connect() as conn:
        conn.execute(text(f"""
            DO $$ BEGIN
                DELETE FROM {schema}.alembic_version
                WHERE version_num NOT IN ({placeholders});
            EXCEPTION WHEN undefined_table THEN NULL;
            END $$
        """))
        conn.commit()


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_object=include_object,
        version_table_schema=DB_SCHEMA,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    _purge_stale_versions(connectable)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_object=include_object,
            version_table_schema=DB_SCHEMA,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
