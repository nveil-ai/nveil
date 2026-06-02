# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""DashboardPanel model — metadata for each panel in a dashboard room."""

import os
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy import ForeignKey

from .base import Base

load_dotenv()

DB_SCHEMA = os.getenv("DATABASE_SCHEMA")


class DashboardPanel(Base):
    __tablename__ = "dashboard_panels"
    __table_args__ = (
        UniqueConstraint("room_id", "panel_id", name="uq_dashboard_panels_room_panel"),
        {"schema": f"{DB_SCHEMA}"},
    )

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    room_id             = Column(UUID(as_uuid=True), ForeignKey(f"{DB_SCHEMA}.rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    panel_id            = Column(String(50), nullable=False)       # "panel_1", "panel_2", ...
    title               = Column(String(255), nullable=False, default="Untitled")
    source_room_id      = Column(UUID(as_uuid=True), ForeignKey(f"{DB_SCHEMA}.rooms.id", ondelete="SET NULL"), nullable=True)
    data_source_config  = Column(Text, nullable=True)               # JSON: [{url, input_id, ...}]
    layout_position     = Column(Text, nullable=True)               # JSON from dockview serialization
    order_index         = Column(Integer, default=0)
    created_at          = Column(DateTime(timezone=True), server_default=func.now())
    updated_at          = Column(DateTime(timezone=True), onupdate=func.now())

    room = relationship("Room", foreign_keys=[room_id], back_populates="dashboard_panels")
    source_room = relationship("Room", foreign_keys=[source_room_id])

    def __repr__(self):
        return f"<DashboardPanel(id={str(self.id)[:5]}, panel_id={self.panel_id}, room={str(self.room_id)[:5]})>"
