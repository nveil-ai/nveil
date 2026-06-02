# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

import enum
import os
from uuid import uuid4
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base
from utils import get_secret

DB_SCHEMA = get_secret("DATABASE_SCHEMA")

class LicenseSeatRole(enum.Enum):
    """License seat role"""
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"

class LicenseSeat(Base):
    """License seat model"""
    __table_args__ = {"schema": f"{DB_SCHEMA}"}
    __tablename__ = "license_seats"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey(f'{DB_SCHEMA}.users.id', ondelete="CASCADE"), nullable=False)
    license_id = Column(UUID(as_uuid=True), ForeignKey(f'{DB_SCHEMA}.licenses.id', ondelete="CASCADE"), nullable=False)
    user = relationship("User", back_populates="license_seats")
    license = relationship("License", back_populates="current_seats")
    role = Column(Enum(LicenseSeatRole), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(),
                        onupdate=datetime.now)

    def __repr__(self) -> str:
        response = f"<LicenseSeat(id={str(self.id)[:5]}, user={str(self.user_id)[:5]}, "
        response += f"license={str(self.license_id)[:5]}, role={self.role})>"
        return response
