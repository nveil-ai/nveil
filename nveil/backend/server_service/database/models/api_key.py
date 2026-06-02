# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from .base import Base
from utils import get_secret

DB_SCHEMA = get_secret("DATABASE_SCHEMA")


class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = {"schema": f"{DB_SCHEMA}"}

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id         = Column(UUID(as_uuid=True), ForeignKey(f"{DB_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False, index=True)
    key_prefix      = Column(String(12), nullable=False)
    key_hash        = Column(String(128), unique=True, nullable=False, index=True)
    name            = Column(String(255), nullable=False)
    scopes          = Column(Text, nullable=False, default="[]")
    is_active       = Column(Boolean, default=True, nullable=False)
    last_used_at    = Column(DateTime(timezone=True), nullable=True)
    expires_at      = Column(DateTime(timezone=True), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at      = Column(DateTime(timezone=True), nullable=True)

    # Usage tracking
    total_requests      = Column(Integer, default=0, nullable=False)
    total_generations   = Column(Integer, default=0, nullable=False)
