# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""UserFile model — tracks user-uploaded data files in the data store."""

import os
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy import Column, DateTime, BigInteger, String, Text, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy import ForeignKey

from .base import Base

load_dotenv()

DB_SCHEMA = os.getenv("DATABASE_SCHEMA")


class UserFile(Base):
    __tablename__ = "user_files"
    __table_args__ = (
        Index("ix_user_files_owner", "owner_id"),
        Index("ix_user_files_owner_name", "owner_id", "original_name", unique=True),
        {"schema": f"{DB_SCHEMA}"},
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    owner_id        = Column(UUID(as_uuid=True), ForeignKey(f"{DB_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False)
    file_id         = Column(UUID(as_uuid=True), nullable=False, unique=True, default=uuid4)
    original_name   = Column(String(500), nullable=False)
    display_name    = Column(String(500), nullable=True)
    format          = Column(String(20), nullable=False)
    size_bytes      = Column(BigInteger, nullable=False)
    sha256          = Column(String(64), nullable=True)
    companion_files = Column(Text, nullable=True)       # JSON array of companion filenames
    processing_status = Column(String(20), nullable=True)  # NULL, 'processing', 'ready', 'error'
    upload_source   = Column(String(20), default="file")  # 'file' or 'url'
    source_url      = Column(Text, nullable=True)
    collection_time_mode = Column(String(20), nullable=True)  # "index" or "time_based" (temporal collection)
    collection_time_delta = Column(String(30), nullable=True) # ISO 8601 duration (e.g. "PT60S")
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("User", foreign_keys=[owner_id])
    room_refs = relationship("RoomDataRef", back_populates="user_file", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<UserFile(id={str(self.id)[:5]}, name={self.original_name})>"
