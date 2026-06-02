# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy import Column, DateTime, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base
from utils import get_secret

DB_SCHEMA = get_secret("DATABASE_SCHEMA")

class	Message(Base):
	__tablename__	= "messages"
	__table_args__	= {"schema": f"{DB_SCHEMA}"}

	id				= Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
	author_id		= Column(UUID(as_uuid=True), ForeignKey(f"{DB_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False)
	room_id			= Column(UUID(as_uuid=True), ForeignKey(f"{DB_SCHEMA}.rooms.id", ondelete="CASCADE"), nullable=False, index=True)
	content			= Column(Text, nullable=False)
	author			= relationship("User", back_populates="messages")
	room			= relationship("Room", back_populates="messages")
	cost			= Column(Float, default=0.0)
	created_at		= Column(DateTime(timezone=True), server_default=func.now())

	def	__repr__(self):
		return f"<Message(id={self.id[:5]}, room_id={self.room_id[:5]}, author_id={self.author_id[:5]})[{self.content}]>"
