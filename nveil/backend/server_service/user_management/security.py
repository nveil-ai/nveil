# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

from datetime import datetime, timedelta
from typing import Optional

import jwt
from utils import get_secret

SECRET_KEY = get_secret("SECRET_KEY")
ALGORITHM = "HS256"

def	create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
	to_encode = data.copy()
	expire =datetime.datetime.utcnow() + (expires_delta or timedelta(minutes=30))
	to_encode.update({"exp": expire})
	return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str) -> dict[str, any]:
	try:
		return jwt.decode(token, SECRET_KEY, algorithms=ALGORITHM)
	except jwt.InvalidTokenError as e:
		return None
