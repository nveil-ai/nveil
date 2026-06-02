# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

import enum
import os
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base
from utils import get_secret

DB_SCHEMA = get_secret("DATABASE_SCHEMA")

class	RoomMemberRole(enum.Enum):
	OWNER	= "owner"
	MEMBER	= "member"

class	RoomType(enum.Enum):
	CHAT		= "chat"
	DASHBOARD	= "dashboard"

class	Room(Base):
	__tablename__	= "rooms"
	__table_args__	= {"schema": f"{DB_SCHEMA}"}

	id				= Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
	name			= Column(String(255), nullable=True)
	owner_id		= Column(UUID(as_uuid=True), ForeignKey(f"{DB_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False)
	type			= Column(Enum(RoomType, values_callable=lambda x: [e.value for e in x], schema=DB_SCHEMA, name="roomtype"), default=RoomType.CHAT, nullable=False, server_default="chat")
	owner			= relationship("User", back_populates="owned_rooms", foreign_keys=[owner_id])
	members			= relationship("RoomMember", back_populates="room", cascade="all, delete-orphan")
	messages		= relationship("Message", back_populates="room", cascade="all, delete-orphan")
	dashboard_panels	= relationship("DashboardPanel", back_populates="room", cascade="all, delete-orphan", foreign_keys="[DashboardPanel.room_id]")
	host			= Column(String, nullable=True, default=None)
	cmd_port		= Column(Integer, nullable=True, default=None)
	viz_port		= Column(Integer, nullable=True, default=None)
	token			= Column(UUID(as_uuid=True), default=uuid4, index=True)
	created_at		= Column(DateTime(timezone=True), server_default=func.now())
	updated_at		= Column(DateTime(timezone=True), onupdate=func.now())
	last_activity	= Column(DateTime(timezone=True), server_default=func.now())

	def	__repr__(self):
		id_str = str(self.id) if self.id is not None else "None"
		owner_str = str(self.owner_id) if self.owner_id is not None else "None"
		return f"<Room(id={id_str[:5]}, owner_id={owner_str[:5]})>"

class	RoomMember(Base):
	__tablename__	= "room_members"
	__table_args__	= (
		Index("ix_room_members_room_user", "room_id", "user_id"),
		{"schema": f"{DB_SCHEMA}"},
	)

	id			= Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
	room_id		= Column(UUID(as_uuid=True), ForeignKey(f"{DB_SCHEMA}.rooms.id", ondelete="CASCADE"), nullable=False)
	user_id		= Column(UUID(as_uuid=True), ForeignKey(f"{DB_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False)
	role		= Column(Enum(RoomMemberRole), default=RoomMemberRole.MEMBER)
	joined_at	= Column(DateTime(timezone=True), server_default=func.now())
	room		= relationship("Room", back_populates="members")
	user		= relationship("User", back_populates="memberships")

	def	__repr__(self):
		return f"<RoomMember(id={self.id[:5]}, room_id={self.room_id[:5]}, user_id={self.user_id[:5]})[{self.role}]>"
