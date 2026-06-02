# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Strip the legacy ``widget_state`` key from every dashboard panel's
``data_source_config`` JSON.

Dashboards now derive widget values from each panel-workspace XML at render
time (the export endpoint bakes the live widget state into the XML before
provisioning). The ``widget_state`` key inside ``data_source_config`` is dead
data. This migration removes it so the column carries only ``url_sources``.

Idempotent: rows whose JSON has no ``widget_state`` key are left alone.

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-13 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
from utils import get_secret

revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = get_secret("DATABASE_SCHEMA", "nveilseption")


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE {SCHEMA}.dashboard_panels
           SET data_source_config = (data_source_config::jsonb - 'widget_state')::text
         WHERE data_source_config IS NOT NULL
           AND data_source_config::jsonb ? 'widget_state'
        """
    )


def downgrade() -> None:
    # widget_state values are not recoverable; downgrade is a no-op.
    pass
