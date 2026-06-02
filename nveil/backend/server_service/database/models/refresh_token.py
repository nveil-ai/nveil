# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from .base import Base
from utils import get_secret

DB_SCHEMA = get_secret("DATABASE_SCHEMA")

class	RefreshToken(Base):
    __tablename__	= "refresh_tokens"
    __table_args__  = (
        Index('idx_token_family_user', 'token_family_id', 'user_id'),
        Index('idx_user_expires', 'user_id', 'expires_at'),
        {"schema": f"{DB_SCHEMA}"},
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    token_hash      = Column(String(255), unique=True, nullable=False, index=True)
    token_family_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    user_id         = Column(UUID(as_uuid=True), ForeignKey(f"{DB_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at      = Column(DateTime, server_default=func.now(), nullable=False)
    expires_at      = Column(DateTime, nullable=False)
    used_at         = Column(DateTime, nullable=False)
    is_revoked      = Column(Boolean, default=False, nullable=False)
    is_used         = Column(Boolean, default=False, nullable=False)
    client_ip       = Column(String(45), nullable=True)
    user_agent      = Column(String(500), nullable=True)

