# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""RoomDataRef model -- links user files to rooms."""

from uuid import uuid4

from shared.secrets import get_secret
from sqlalchemy import Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from .base import Base

DB_SCHEMA = get_secret("DATABASE_SCHEMA")


class RoomDataRef(Base):
    __tablename__ = "room_data_refs"
    __table_args__ = (
        Index("ix_room_data_refs_room", "room_id"),
        Index("ix_room_data_refs_file", "user_file_id"),
        {"schema": f"{DB_SCHEMA}"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    # FK constraint to rooms.id exists at DB level (Alembic). No SQLAlchemy
    # ForeignKey here because the Room model lives in server_service.
    room_id = Column(UUID(as_uuid=True), nullable=False)
    # FK to user_files.id also managed at DB level.
    user_file_id = Column(UUID(as_uuid=True), nullable=False)
    panel_id = Column(String(50), nullable=True)
    linked_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<RoomDataRef(room={str(self.room_id)[:5]}, file={str(self.user_file_id)[:5]}, panel={self.panel_id})>"
