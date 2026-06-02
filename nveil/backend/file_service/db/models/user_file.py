# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""UserFile model -- tracks user-uploaded data files in the data store."""

from uuid import uuid4

from shared.secrets import get_secret
from sqlalchemy import BigInteger, Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from .base import Base

DB_SCHEMA = get_secret("DATABASE_SCHEMA")


class UserFile(Base):
    __tablename__ = "user_files"
    __table_args__ = (
        Index("ix_user_files_owner", "owner_id"),
        Index("ix_user_files_owner_name", "owner_id", "original_name", unique=True),
        {"schema": f"{DB_SCHEMA}"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    # FK constraint to users.id exists at DB level (Alembic). No SQLAlchemy
    # ForeignKey here because the User model lives in server_service.
    owner_id = Column(UUID(as_uuid=True), nullable=False)
    file_id = Column(UUID(as_uuid=True), nullable=False, unique=True, default=uuid4)
    original_name = Column(String(500), nullable=False)
    display_name = Column(String(500), nullable=True)
    format = Column(String(20), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=True)
    companion_files = Column(Text, nullable=True)  # JSON array of companion filenames
    processing_status = Column(String(20), nullable=True)  # NULL, 'processing', 'ready', 'error'
    upload_source = Column(String(20), default="file")  # 'file' or 'url'
    source_url = Column(Text, nullable=True)
    collection_time_mode = Column(String(20), nullable=True)   # "index" or "time_based" (temporal collection)
    collection_time_delta = Column(String(30), nullable=True)  # ISO 8601 duration (e.g. "PT60S")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<UserFile(id={str(self.id)[:5]}, name={self.original_name})>"
