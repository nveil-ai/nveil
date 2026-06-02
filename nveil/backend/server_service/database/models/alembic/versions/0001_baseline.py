# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""baseline — consolidated schema

Squashes all prior migrations into a single idempotent script.
Every operation uses IF NOT EXISTS / DO $$ guards so
``alembic upgrade head`` is safe on both fresh and existing databases.

Prior revisions replaced:
  08c6de756e8e  add_email_verified
  a1b2c3d4e5f6  add_is_guest_column
  b7c8d9e0f1a2  add_indexes
  bfb53d75a6b0  add_active_license_id
  c3d4e5f6a7b8  add_dashboard_models
  1cd01fcdd62f  source_room_id_fix
  d4e5f6a7b8c9  nullify_room_viz_defaults
  e5f6a7b8c9d0  add_user_files_and_room_data_refs
  f6a7b8c9d0e1  add_processing_status_to_user_files
  a7b8c9d0e1f2  add_panel_id_to_room_data_refs

Revision ID: 0001
Revises:
Create Date: 2026-03-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from helpers import safe_create_enum
from utils import get_secret

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = get_secret("DATABASE_SCHEMA", "nveilseption")

def upgrade() -> None:
    # ── 1. Enum types ───────────────────────────────────────────────
    safe_create_enum("roomtype", ["chat", "dashboard"], SCHEMA)

    # ── 2. Extend existing tables ───────────────────────────────────

    # users
    op.execute(
        f"ALTER TABLE {SCHEMA}.users "
        f"ADD COLUMN IF NOT EXISTS email_verified BOOLEAN"
    )
    op.execute(
        f"ALTER TABLE {SCHEMA}.users "
        f"ADD COLUMN IF NOT EXISTS is_guest BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        f"ALTER TABLE {SCHEMA}.users "
        f"ADD COLUMN IF NOT EXISTS active_license_id UUID"
    )

    # rooms
    op.execute(
        f"ALTER TABLE {SCHEMA}.rooms "
        f"ADD COLUMN IF NOT EXISTS type {SCHEMA}.roomtype "
        f"NOT NULL DEFAULT 'chat'::{SCHEMA}.roomtype"
    )
    op.execute(
        f"ALTER TABLE {SCHEMA}.rooms "
        f"ADD COLUMN IF NOT EXISTS name VARCHAR(255)"
    )

    # ── 3. New tables (final state) ─────────────────────────────────

    # dashboard_panels
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.dashboard_panels (
            id              UUID NOT NULL,
            room_id         UUID NOT NULL,
            panel_id        VARCHAR(50) NOT NULL,
            title           VARCHAR(255) NOT NULL DEFAULT 'Untitled',
            source_room_id  UUID,
            data_source_config TEXT,
            layout_position TEXT,
            order_index     INTEGER DEFAULT 0,
            created_at      TIMESTAMPTZ DEFAULT now(),
            updated_at      TIMESTAMPTZ,
            CONSTRAINT pk_dashboard_panels PRIMARY KEY (id),
            CONSTRAINT fk_dashboard_panels_room_id_rooms
                FOREIGN KEY (room_id) REFERENCES {SCHEMA}.rooms(id),
            CONSTRAINT fk_dashboard_panels_source_room_id_rooms
                FOREIGN KEY (source_room_id) REFERENCES {SCHEMA}.rooms(id)
                ON DELETE SET NULL,
            CONSTRAINT uq_dashboard_panels_room_panel
                UNIQUE (room_id, panel_id)
        )
    """)

    # user_files
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.user_files (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_id        UUID NOT NULL
                REFERENCES {SCHEMA}.users(id) ON DELETE CASCADE,
            file_id         UUID NOT NULL UNIQUE,
            original_name   VARCHAR(500) NOT NULL,
            display_name    VARCHAR(500),
            format          VARCHAR(20) NOT NULL,
            size_bytes      BIGINT NOT NULL,
            sha256          VARCHAR(64),
            companion_files TEXT,
            processing_status VARCHAR(20),
            upload_source   VARCHAR(20) DEFAULT 'file',
            source_url      TEXT,
            created_at      TIMESTAMPTZ DEFAULT now(),
            updated_at      TIMESTAMPTZ DEFAULT now()
        )
    """)

    # room_data_refs
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.room_data_refs (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            room_id         UUID NOT NULL
                REFERENCES {SCHEMA}.rooms(id) ON DELETE CASCADE,
            user_file_id    UUID NOT NULL
                REFERENCES {SCHEMA}.user_files(id) ON DELETE CASCADE,
            panel_id        VARCHAR(50),
            linked_at       TIMESTAMPTZ DEFAULT now()
        )
    """)

    # ── 4. Indexes ──────────────────────────────────────────────────

    # existing tables
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_rooms_token ON {SCHEMA}.rooms(token)")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_messages_room_id ON {SCHEMA}.messages(room_id)")
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_room_members_room_user "
        f"ON {SCHEMA}.room_members(room_id, user_id)"
    )

    # dashboard_panels
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_dashboard_panels_room_id "
        f"ON {SCHEMA}.dashboard_panels(room_id)"
    )

    # user_files
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_user_files_owner ON {SCHEMA}.user_files(owner_id)")
    op.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS ix_user_files_owner_name "
        f"ON {SCHEMA}.user_files(owner_id, original_name)"
    )

    # room_data_refs
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_room_data_refs_room ON {SCHEMA}.room_data_refs(room_id)")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_room_data_refs_file ON {SCHEMA}.room_data_refs(user_file_id)")
    op.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS uq_room_data_refs_room_file_panel "
        f"ON {SCHEMA}.room_data_refs(room_id, user_file_id, COALESCE(panel_id, ''))"
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_room_data_refs_panel "
        f"ON {SCHEMA}.room_data_refs(panel_id) WHERE panel_id IS NOT NULL"
    )

    # ── 5. Data cleanup (idempotent UPDATEs) ────────────────────────
    op.execute(f"UPDATE {SCHEMA}.rooms SET host = NULL WHERE host = 'localhost'")
    op.execute(f"UPDATE {SCHEMA}.rooms SET cmd_port = NULL WHERE cmd_port = 0")
    op.execute(f"UPDATE {SCHEMA}.rooms SET viz_port = NULL WHERE viz_port = 0")


def downgrade() -> None:
    # Drop new tables (reverse dependency order)
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.room_data_refs")
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.user_files")
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.dashboard_panels")

    # Drop added columns
    op.execute(f"ALTER TABLE {SCHEMA}.rooms DROP COLUMN IF EXISTS name")
    op.execute(f"ALTER TABLE {SCHEMA}.rooms DROP COLUMN IF EXISTS type")
    op.execute(f"ALTER TABLE {SCHEMA}.users DROP COLUMN IF EXISTS active_license_id")
    op.execute(f"ALTER TABLE {SCHEMA}.users DROP COLUMN IF EXISTS is_guest")
    op.execute(f"ALTER TABLE {SCHEMA}.users DROP COLUMN IF EXISTS email_verified")

    # Drop enum
    op.execute(f"DROP TYPE IF EXISTS {SCHEMA}.roomtype")

    # Drop indexes on pre-existing tables
    op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.ix_rooms_token")
    op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.ix_messages_room_id")
    op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.ix_room_members_room_user")
