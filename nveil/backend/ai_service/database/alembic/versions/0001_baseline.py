# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""baseline — AI service schema

Creates user_properties (the only active table) and drops the dead
user_state table on existing deployments.  All operations are
idempotent so ``alembic upgrade head`` is safe on both fresh and
existing databases.

Revision ID: 0001
Revises:
Create Date: 2026-03-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from shared.secrets import get_secret

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = get_secret("STATE_DATABASE_SCHEMA", "state_schema")


def upgrade() -> None:
    # Create user_properties if not exists (for fresh deploys)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.user_properties (
            user_id VARCHAR PRIMARY KEY,
            tone VARCHAR,
            compl_info TEXT
        )
    """)
    # Drop dead table on existing deploys
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.user_state")


def downgrade() -> None:
    # Recreate user_state if rolling back
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.user_state (
            room_id VARCHAR PRIMARY KEY,
            state JSONB NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
