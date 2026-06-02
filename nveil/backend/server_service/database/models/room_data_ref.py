# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""RoomDataRef model — links user files to rooms."""

import os
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy import Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy import ForeignKey

from .base import Base

load_dotenv()

DB_SCHEMA = os.getenv("DATABASE_SCHEMA")


class RoomDataRef(Base):
    __tablename__ = "room_data_refs"
    __table_args__ = (
        Index("ix_room_data_refs_room", "room_id"),
        Index("ix_room_data_refs_file", "user_file_id"),
        {"schema": f"{DB_SCHEMA}"},
    )

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    room_id       = Column(UUID(as_uuid=True), ForeignKey(f"{DB_SCHEMA}.rooms.id", ondelete="CASCADE"), nullable=False)
    user_file_id  = Column(UUID(as_uuid=True), ForeignKey(f"{DB_SCHEMA}.user_files.id", ondelete="CASCADE"), nullable=False)
    panel_id      = Column(String(50), nullable=True)
    linked_at     = Column(DateTime(timezone=True), server_default=func.now())

    room = relationship("Room", foreign_keys=[room_id])
    user_file = relationship("UserFile", back_populates="room_refs")

    def __repr__(self):
        return f"<RoomDataRef(room={str(self.room_id)[:5]}, file={str(self.user_file_id)[:5]}, panel={self.panel_id})>"
