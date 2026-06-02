# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
from uuid import uuid4
from datetime import datetime

from dotenv import load_dotenv

from sqlalchemy import Boolean, Column, DateTime, Integer, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base
from utils import get_secret

DB_SCHEMA = get_secret("DATABASE_SCHEMA")

class License(Base):
    """License for user or for entreprise"""
    __table_args__ = {"schema": f"{DB_SCHEMA}"}
    __tablename__ = "licenses"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    license_name = Column(String, nullable=False)
    owner_id = Column(UUID(as_uuid=True), ForeignKey(f'{DB_SCHEMA}.users.id', ondelete="CASCADE"), nullable=False)
    owner = relationship("User", back_populates="owned_licenses", foreign_keys=[owner_id])
    customer_id = Column(String, nullable=False)
    subscription_id = Column(String, nullable=False)
    max_seats = Column(Integer, nullable=False, default=1)
    current_seats = relationship("LicenseSeat", back_populates="license",
                                 cascade="all, delete-orphan")
    is_active = Column(Boolean, nullable=False)
    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=False)
    expired_at = Column(DateTime(timezone=True), nullable=True)
    retractation_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(),
                        onupdate=datetime.now)

    def __repr__(self) -> str:
        response = f"<License(id={str(self.id)[:5]}, name={self.license_name}, "
        response += f"owner={str(self.owner_id)[:5]}, active={self.is_active})>"
        return response
