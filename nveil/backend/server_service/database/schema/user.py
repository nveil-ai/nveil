# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

from typing import Optional

from pydantic import BaseModel, ConfigDict


class UserUpdate(BaseModel):
	email: str
	first_name: Optional[str] = None
	last_name: Optional[str] = None
	country: Optional[str] = None
	profession: Optional[str] = None
	education: Optional[str] = None
	is_professional: Optional[bool] = None
	enterprise_name: Optional[str] = None
	phone_number: Optional[str] = None
	accept_cgu: Optional[bool] = None
	accept_privacy: Optional[bool] = None
	accept_communication: Optional[bool] = None
	email_verified: Optional[bool] = None

class UserCreate(UserUpdate):
	name: str
	email: str
	password: str

class	UserLogin(BaseModel):
	email:		str
	password:	str

class	UserResponse(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	name:	str
	email: str
	first_name: Optional[str] = None
	last_name: Optional[str] = None
	country: Optional[str] = None
	profession: Optional[str] = None
	education: Optional[str] = None
	is_professional: Optional[bool] = None
	enterprise_name: Optional[str] = None
	phone_number: Optional[str] = None
	accept_cgu: Optional[bool] = None
	accept_privacy: Optional[bool] = None
	accept_communication: Optional[bool] = None
	email_verified: Optional[bool] = None
	is_guest: Optional[bool] = False
