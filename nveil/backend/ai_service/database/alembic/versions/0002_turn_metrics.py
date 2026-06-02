# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""add turn_metrics table

Stores per-turn LLM cost and timing metrics with per-attempt
columns for planning_transformation and xml_generation retries.

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-16 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
from shared.secrets import get_secret

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = get_secret("STATE_DATABASE_SCHEMA", "state_schema")


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.turn_metrics (
            id              SERIAL PRIMARY KEY,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            room_id         VARCHAR,
            owner_id        VARCHAR,
            user_id         VARCHAR,

            -- Entry classification
            entry_classif_elapsed_s        REAL,
            entry_classif_input_tokens     INTEGER,
            entry_classif_cached_tokens    INTEGER,
            entry_classif_output_tokens    INTEGER,
            entry_classif_thinking_tokens  INTEGER,

            -- Planning transformation (up to 3 attempts)
            planning_retries               INTEGER DEFAULT 0,

            planning_1st_elapsed_s         REAL,
            planning_1st_input_tokens      INTEGER,
            planning_1st_cached_tokens     INTEGER,
            planning_1st_output_tokens     INTEGER,
            planning_1st_thinking_tokens   INTEGER,

            planning_2nd_elapsed_s         REAL,
            planning_2nd_input_tokens      INTEGER,
            planning_2nd_cached_tokens     INTEGER,
            planning_2nd_output_tokens     INTEGER,
            planning_2nd_thinking_tokens   INTEGER,

            planning_3rd_elapsed_s         REAL,
            planning_3rd_input_tokens      INTEGER,
            planning_3rd_cached_tokens     INTEGER,
            planning_3rd_output_tokens     INTEGER,
            planning_3rd_thinking_tokens   INTEGER,

            -- XML generation (up to 3 attempts)
            xml_gen_retries                INTEGER DEFAULT 0,

            xml_gen_1st_elapsed_s          REAL,
            xml_gen_1st_input_tokens       INTEGER,
            xml_gen_1st_cached_tokens      INTEGER,
            xml_gen_1st_output_tokens      INTEGER,
            xml_gen_1st_thinking_tokens    INTEGER,

            xml_gen_2nd_elapsed_s          REAL,
            xml_gen_2nd_input_tokens       INTEGER,
            xml_gen_2nd_cached_tokens      INTEGER,
            xml_gen_2nd_output_tokens      INTEGER,
            xml_gen_2nd_thinking_tokens    INTEGER,

            xml_gen_3rd_elapsed_s          REAL,
            xml_gen_3rd_input_tokens       INTEGER,
            xml_gen_3rd_cached_tokens      INTEGER,
            xml_gen_3rd_output_tokens      INTEGER,
            xml_gen_3rd_thinking_tokens    INTEGER,

            -- Keyword classification
            keyword_classif_elapsed_s      REAL,
            keyword_classif_input_tokens   INTEGER,
            keyword_classif_cached_tokens  INTEGER,
            keyword_classif_output_tokens  INTEGER,
            keyword_classif_thinking_tokens INTEGER,

            -- Exclusion processing
            exclusion_elapsed_s            REAL,
            exclusion_input_tokens         INTEGER,
            exclusion_cached_tokens        INTEGER,
            exclusion_output_tokens        INTEGER,
            exclusion_thinking_tokens      INTEGER,

            -- Totals
            total_elapsed_s                REAL,
            total_input_tokens             INTEGER,
            total_cached_tokens            INTEGER,
            total_output_tokens            INTEGER,
            total_thinking_tokens          INTEGER
        )
    """)
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_turn_metrics_room_id ON {SCHEMA}.turn_metrics (room_id)")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_turn_metrics_created_at ON {SCHEMA}.turn_metrics (created_at)")


def downgrade() -> None:
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.turn_metrics")
