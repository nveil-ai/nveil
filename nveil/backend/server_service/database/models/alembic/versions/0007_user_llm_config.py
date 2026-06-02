# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Add user_llm_config table for per-user LLM provider + encrypted API key.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from utils import get_secret

revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = get_secret("DATABASE_SCHEMA", "nveilseption")


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.user_llm_config (
            user_id           UUID PRIMARY KEY REFERENCES {SCHEMA}.users(id) ON DELETE CASCADE,
            provider          VARCHAR(32) NOT NULL,
            api_key_encrypted TEXT NOT NULL,
            api_key_suffix    VARCHAR(8) NOT NULL,
            base_url          VARCHAR(512),
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ
        )
    """)


def downgrade() -> None:
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.user_llm_config CASCADE")
