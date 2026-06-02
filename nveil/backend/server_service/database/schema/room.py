# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

class	RoomResponse(BaseModel):
	id:			UUID
	ownener_id:	UUID
	created_at:	datetime

	class Config:
		from_attributes = True
