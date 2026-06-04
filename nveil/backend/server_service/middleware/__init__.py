# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Middleware package for FastAPI server."""

from .security_headers import SecurityHeadersMiddleware

__all__ = ["SecurityHeadersMiddleware"]
