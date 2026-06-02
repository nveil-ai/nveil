# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Serve pre-compressed static assets (.br / .gz) when available.

Vite generates .br and .gz variants of every JS/CSS chunk at build time.
This middleware intercepts requests for /assets/ files, negotiates the
best encoding via Accept-Encoding, and serves the pre-built file directly
— avoiding on-the-fly compression from GZipMiddleware for these assets.
"""

import mimetypes
import os

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import FileResponse
from starlette.types import ASGIApp, Receive, Scope, Send


# Encodings in preference order (brotli is smaller than gzip)
_ENCODINGS = [
    ("br", ".br"),
    ("gzip", ".gz"),
]


class PreCompressedStaticMiddleware:
    """ASGI middleware that serves pre-compressed .br/.gz static assets.

    Covers /assets/ (Vite-built JS/CSS chunks) AND /vendor/ (self-hosted
    plotly/deckgl/maplibre bundles produced by scripts/fetch-vendor-cdn.mjs).
    Both use version-hashed/pinned filenames and get 1-year immutable caching.
    """

    # Prefix → on-disk directory. All prefixes are treated as immutable.
    _PREFIXES = ("/assets/", "/vendor/")

    def __init__(self, app: ASGIApp, frontend_dir: str):
        self.app = app
        self.frontend_dir = os.path.abspath(frontend_dir)

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")

        matched_prefix = next((p for p in self._PREFIXES if path.startswith(p)), None)
        if matched_prefix is None:
            await self.app(scope, receive, send)
            return

        # Resolve the original file on disk (keep the prefix — file lives at
        # frontend_dir/assets/... or frontend_dir/vendor/...).
        relative = path.lstrip("/")
        original = os.path.join(self.frontend_dir, relative)

        if not os.path.isfile(original):
            await self.app(scope, receive, send)
            return

        content_type, _ = mimetypes.guess_type(original)
        if not content_type:
            content_type = "application/octet-stream"

        _IMMUTABLE = "public, max-age=31536000, immutable"

        # For JS/CSS/MJS, try to serve pre-compressed .br/.gz variants
        if path.endswith((".js", ".mjs", ".css")):
            request = Request(scope)
            accept = request.headers.get("accept-encoding", "")

            for encoding, ext in _ENCODINGS:
                if encoding not in accept:
                    continue
                compressed_path = original + ext
                if os.path.isfile(compressed_path):
                    response = FileResponse(
                        compressed_path,
                        media_type=content_type,
                        headers={
                            "Content-Encoding": encoding,
                            "Cache-Control": _IMMUTABLE,
                            "Vary": "Accept-Encoding",
                        },
                    )
                    await response(scope, receive, send)
                    return

        # Uncompressed fallback — fonts, images, any file without a .br/.gz.
        response = FileResponse(
            original,
            media_type=content_type,
            headers={"Cache-Control": _IMMUTABLE},
        )
        await response(scope, receive, send)
