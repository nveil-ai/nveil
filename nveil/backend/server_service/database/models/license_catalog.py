# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
from uuid import uuid4

from sqlalchemy import Column, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from .base import Base
from utils import get_secret

DB_SCHEMA = get_secret("DATABASE_SCHEMA")

class LicenseCatalog(Base):
    """License catalog model"""
    __tablename__ = "license_catalog"
    __table_args__ = (
        UniqueConstraint("license", "feature", name="uix_license_feature"),
        {"schema": f"{DB_SCHEMA}"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    license = Column(Text, nullable=False, doc="License name")
    feature = Column(Text, nullable=False, doc="Feature name")
    value = Column(Text, nullable=False, doc="Feature value")

    def __repr__(self) -> str:
        response = f"<LicenseCatalog(id={str(self.id)[:5]}, license={self.license}, "
        response += f"feature={self.feature}, value={self.value})>"
        return response
