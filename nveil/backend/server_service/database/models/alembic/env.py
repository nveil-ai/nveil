# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

# Add the path to the server_service directory to sys.path
# env.py is in /workspaces/app/nveil/backend/server_service/database/models/alembic/
# We want /workspaces/app/nveil/backend/server_service/
current_dir = os.path.dirname(os.path.abspath(__file__))
server_service_dir = os.path.abspath(os.path.join(current_dir, "../../../"))
sys.path.append(server_service_dir)
# Also add alembic/ dir so migration scripts can `from helpers import ...`
sys.path.append(current_dir)

# Import Base and all models so autogenerate sees every table
from database.models.base import Base
from database.models import user, room, message, refresh_token, license, license_catalog, license_seat, dashboard_panel, user_file, room_data_ref, api_key
from utils import get_secret

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set sqlalchemy.url from environment variable
db_url = get_secret("DATABASE_URL")
if db_url:
    # Swap the async asyncpg dialect for psycopg v3, which Alembic runs synchronously.
    config.set_main_option("sqlalchemy.url", db_url.replace("+asyncpg", "+psycopg"))

target_metadata = Base.metadata

DB_SCHEMA = get_secret("DATABASE_SCHEMA")

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
    """Clear alembic_version rows whose revision no longer exists in the migration chain.

    Uses its OWN connection so it doesn't interfere with Alembic's transaction
    management on the main connection.
    """
    from alembic.script import ScriptDirectory
    script_dir = ScriptDirectory.from_config(config)
    known_revs = {r.revision for r in script_dir.walk_revisions()}

    if not known_revs:
        return

    schema = DB_SCHEMA or "nveilseption"
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
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
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
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # Purge stale revisions in a SEPARATE connection — must not touch
    # the connection Alembic will use, otherwise autobegin corrupts
    # Alembic's transaction and DDL silently rolls back.
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
