# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

from pydantic import BaseModel


class   TokenOut(BaseModel):
    access_token:   str
    refresh_token:  str
    token_type:     str = "bearer"
    expires_in:     int

class   RefreshRequest(BaseModel):
    refresh_token: str
