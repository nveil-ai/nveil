# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Add api_keys table for public API authentication.

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from utils import get_secret

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = get_secret("DATABASE_SCHEMA", "nveilseption")


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.api_keys (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         UUID NOT NULL REFERENCES {SCHEMA}.users(id),
            key_prefix      VARCHAR(12) NOT NULL,
            key_hash        VARCHAR(128) UNIQUE NOT NULL,
            name            VARCHAR(255) NOT NULL,
            scopes          TEXT NOT NULL DEFAULT '[]',
            is_active       BOOLEAN NOT NULL DEFAULT true,
            last_used_at    TIMESTAMPTZ,
            expires_at      TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            revoked_at      TIMESTAMPTZ,
            total_requests      INTEGER NOT NULL DEFAULT 0,
            total_generations   INTEGER NOT NULL DEFAULT 0
        )
    """)

    op.execute(f"""
        CREATE INDEX IF NOT EXISTS ix_api_keys_user_id
            ON {SCHEMA}.api_keys (user_id)
    """)

    op.execute(f"""
        CREATE UNIQUE INDEX IF NOT EXISTS ix_api_keys_key_hash
            ON {SCHEMA}.api_keys (key_hash)
    """)


def downgrade() -> None:
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.api_keys CASCADE")
