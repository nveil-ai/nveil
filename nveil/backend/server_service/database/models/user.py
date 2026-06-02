# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base
from utils import get_secret

DB_SCHEMA = get_secret("DATABASE_SCHEMA")

class ConnectionLog(Base):
	"""
	Obligation CPCE Art. L. 34-1 (Loi Anti-terrorisme).
	Conservation stricte des IPs pendant 1 an.
	"""
	__table_args__	= {"schema": f"{DB_SCHEMA}"}
	__tablename__ = 'connection_logs'

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
	user_id = Column(UUID(as_uuid=True), ForeignKey(f'{DB_SCHEMA}.users.id', ondelete="CASCADE"), nullable=False)
	
	timestamp = Column(DateTime(timezone=True), server_default=func.now())
	ip_address = Column(String(45), nullable=False)
	action = Column(String(50), nullable=False) # "LOGIN", "LOGOUT", "FAILED_LOGIN"

	user = relationship("User", back_populates="connection_logs")

class	User(Base):
	__tablename__	= "users"
	__table_args__	= {"schema": f"{DB_SCHEMA}"}

	id				= Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
	name			= Column(String, index=True)
	first_name     = Column(String, nullable=True)
	last_name      = Column(String, nullable=True)
	email			= Column(String, unique=True, index=True)
	_password		= Column(String, nullable=True)

	country		= Column(String, nullable=True)
	profession		= Column(String, nullable=True)
	education		= Column(String, nullable=True)
	is_professional	= Column(Boolean, nullable=True)
	enterprise_name	= Column(String, nullable=True)
	phone_number		= Column(String, nullable=True)
	accept_cgu = Column(Boolean, nullable=True)
	accept_privacy = Column(Boolean, nullable=True)
	accept_communication = Column(Boolean, nullable=True)
	email_verified = Column(Boolean, default=False)
	is_guest = Column(Boolean, default=False)

	active_license_id = Column(UUID(as_uuid=True), nullable=True)
	
	# Relations
	owned_licenses = relationship("License", back_populates="owner", foreign_keys="License.owner_id")

	connection_logs = relationship("ConnectionLog", back_populates="user")

	owned_rooms		= relationship("Room", back_populates="owner", foreign_keys="Room.owner_id")
	memberships		= relationship("RoomMember", back_populates="user", cascade="all, delete-orphan")
	messages		= relationship("Message", back_populates="author", cascade="all, delete-orphan")
	license_seats	= relationship("LicenseSeat", back_populates="user", cascade="all, delete-orphan")
	created_at		= Column(DateTime(timezone=True), server_default=func.now())
	updated_at		= Column(DateTime(timezone=True), onupdate=func.now())
	last_seen		= Column(DateTime(timezone=True))
	is_online		= Column(Boolean, default=False)

	@property
	def masked_password(self):
		return "*****" if self._password else None

	def	__repr__(self):
		return f"<User(id={self.id[:5]}, name={self.name}, email={self.email})>"
