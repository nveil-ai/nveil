# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Shared error codes for inter-service communication.

The frontend can key on ``error_code`` to show targeted messages.
"""

from enum import Enum


class ErrorCode(str, Enum):
    AI_UNAVAILABLE = "AI_UNAVAILABLE"
    VIZ_UNAVAILABLE = "VIZ_UNAVAILABLE"
    ASP_TIMEOUT = "ASP_TIMEOUT"
    LLM_FAILED = "LLM_FAILED"
    METADATA_ERROR = "METADATA_ERROR"
    ROOM_NOT_READY = "ROOM_NOT_READY"
    GUEST_LIMIT = "GUEST_LIMIT"
    INVALID_REQUEST = "INVALID_REQUEST"
