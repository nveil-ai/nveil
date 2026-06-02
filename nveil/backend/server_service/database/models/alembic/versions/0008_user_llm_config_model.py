# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Add `model` column to user_llm_config (per-user model override).

Used when the user picks a provider whose default yaml model is wrong
for their endpoint (typically Ollama or OpenAI-via-OpenRouter, where
the provider yaml says `gpt-4o-mini` but the user wants something else).

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from utils import get_secret

revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = get_secret("DATABASE_SCHEMA", "nveilseption")


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE {SCHEMA}.user_llm_config "
        f"ADD COLUMN IF NOT EXISTS model VARCHAR(128)"
    )


def downgrade() -> None:
    op.execute(
        f"ALTER TABLE {SCHEMA}.user_llm_config "
        f"DROP COLUMN IF EXISTS model"
    )
