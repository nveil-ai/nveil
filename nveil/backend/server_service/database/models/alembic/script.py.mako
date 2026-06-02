"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from helpers import safe_create_enum, safe_add_fk, safe_add_unique
from utils import get_secret
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}

SCHEMA = get_secret("DATABASE_SCHEMA", "nveilseption")

# ── IMPORTANT: all operations MUST be idempotent ───────────────────────
#
#   Column:  op.execute(f"ALTER TABLE {SCHEMA}.t ADD COLUMN IF NOT EXISTS col TYPE")
#   Table:   op.execute(f"CREATE TABLE IF NOT EXISTS {SCHEMA}.t (...)")
#   Index:   op.execute(f"CREATE INDEX IF NOT EXISTS idx ON {SCHEMA}.t(col)")
#   Enum:    safe_create_enum("name", ["a", "b"], SCHEMA)
#   FK:      safe_add_fk("table", "fk_name", "FOREIGN KEY ...", SCHEMA)
#   Unique:  safe_add_unique("table", "uq_name", "col1, col2", SCHEMA)
#   Drop:    op.execute(f"DROP ... IF EXISTS ...")
#
# Do NOT use bare op.add_column / op.create_index — they crash on re-run.
# After autogenerate, convert each operation to its idempotent form above.
# ───────────────────────────────────────────────────────────────────────


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
