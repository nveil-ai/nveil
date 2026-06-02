# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Add temporal collection columns to user_files.

A temporal collection is a UserFile where collection_time_mode is set.
The actual file members are stored as companion_files (same as DICOM).
Time configuration is stored on the record for use at link time.

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-28 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from utils import get_secret

revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = get_secret("DATABASE_SCHEMA", "nveilseption")


def upgrade() -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.user_files ADD COLUMN IF NOT EXISTS collection_time_mode VARCHAR(20)")
    op.execute(f"ALTER TABLE {SCHEMA}.user_files ADD COLUMN IF NOT EXISTS collection_time_delta VARCHAR(30)")
    # Drop collection_id if it exists from a previous version of this migration
    op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.ix_user_files_collection")
    op.execute(f"ALTER TABLE {SCHEMA}.user_files DROP COLUMN IF EXISTS collection_id")


def downgrade() -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.user_files DROP COLUMN IF EXISTS collection_time_delta")
    op.execute(f"ALTER TABLE {SCHEMA}.user_files DROP COLUMN IF EXISTS collection_time_mode")
