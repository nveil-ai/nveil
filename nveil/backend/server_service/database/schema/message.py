# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

from datetime import datetime

from pydantic import BaseModel, ConfigDict

class	MessageCreate(BaseModel):
	content:	str

class	MessageResponse(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id:				str
	content:		str
	room_token:		str
	author_email:	str
	created_at:		datetime
