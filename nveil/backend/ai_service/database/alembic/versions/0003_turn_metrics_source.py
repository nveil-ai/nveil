# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""add source column to turn_metrics

Distinguishes SDK vs web usage.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-09 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from shared.secrets import get_secret

# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = get_secret("STATE_DATABASE_SCHEMA", "state_schema")


def upgrade() -> None:
    op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = '{_SCHEMA}'
                  AND table_name = 'turn_metrics'
                  AND column_name = 'source'
            ) THEN
                ALTER TABLE {_SCHEMA}.turn_metrics
                    ADD COLUMN source VARCHAR DEFAULT 'web';
            END IF;
        END $$;
    """)
    op.execute(f"UPDATE {_SCHEMA}.turn_metrics SET source = 'web' WHERE source IS NULL")


def downgrade() -> None:
    op.drop_column('turn_metrics', 'source', schema=_SCHEMA)
