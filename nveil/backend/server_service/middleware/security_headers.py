# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Security headers middleware for FastAPI."""

from utils import get_secret

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Check environment
IS_PRODUCTION = get_secret("GCP") == "1" or get_secret("ENV") == "production"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all responses.

    Headers added:
    - Strict-Transport-Security (HSTS)
    - Content-Security-Policy (CSP)
    - X-Content-Type-Options
    - X-Frame-Options
    - X-XSS-Protection
    - Referrer-Policy
    - Permissions-Policy
    - Cross-Origin-Resource-Policy
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        path = request.url.path

        # /viz/* and /kedro-viz/* are proxied to third-party services (Trame,
        # Kedro Viz) whose HTML we don't own — they contain inline scripts and
        # load runtime CDN dependencies (unpkg.com, esm.sh) we cannot restrict.
        # Both paths are behind authentication, so the relaxed policy is scoped.
        is_viz_route = path.startswith("/viz/") or path.startswith("/kedro-viz/")

        # Strict-Transport-Security: Force HTTPS for 1 year, include subdomains
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

        # Content-Security-Policy: Defence against XSS.
        #
        # 'unsafe-inline' is required by the inline GTM consent + loader blocks
        # in index.html. 'unsafe-eval' is required by VTK.js (compiles WebGL
        # shaders via new Function() at runtime).
        #
        # Viz/Kedro routes additionally allow unpkg.com and esm.sh because the
        # DIVE graph library (force-graph, 3d-force-graph, three-spritetext)
        # loads them dynamically at runtime.
        if is_viz_route:
            script_src = (
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
                "https://accounts.google.com https://www.googletagmanager.com "
                "https://www.google-analytics.com https://feedback.nveil.com "
                "https://unpkg.com https://esm.sh "
                "https://www.redditstatic.com https://snap.licdn.com "
                "https://connect.facebook.net blob:"
            )
        else:
            # Heavy viz libs (plotly, maplibre, deck.gl) are now served from
            # our own /vendor/ directory via the importmap in index.html — no
            # third-party CDN allowance needed in script-src.
            script_src = (
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
                "https://accounts.google.com https://www.googletagmanager.com "
                "https://www.google-analytics.com https://feedback.nveil.com "
                "https://www.redditstatic.com https://snap.licdn.com "
                "https://connect.facebook.net blob:"
            )

        csp_directives = [
            "default-src 'self'",
            script_src,
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://accounts.google.com https://api.tiles.mapbox.com https://api.mapbox.com",
            "font-src 'self' https://fonts.gstatic.com data:",
            "img-src 'self' data: blob: https: http: https://*.reddit.com https://www.redditstatic.com https://*.google-analytics.com https://*.doubleclick.net https://px.ads.linkedin.com https://www.facebook.com",
            "connect-src 'self' https://app.nveil.com https://accounts.google.com https://oauth2.googleapis.com https://feedback.nveil.com https://*.google-analytics.com https://*.analytics.google.com https://*.stats.g.doubleclick.net https://unpkg.com https://esm.sh https://*.reddit.com https://www.redditstatic.com https://alb.reddit.com https://*.linkedin.com https://*.licdn.com https://*.facebook.com https://*.cartocdn.com https://*.mapbox.com wss://app.nveil.com wss://localhost:* https://localhost:*",
            "frame-src 'self' https://accounts.google.com https://feedback.nveil.com https://js.stripe.com https://www.youtube-nocookie.com https://www.youtube.com",
            "frame-ancestors 'self'",
            "form-action 'self'",
            "base-uri 'self'",
            "object-src 'none'",
            "worker-src 'self' blob:",
        ]

        # Add upgrade-insecure-requests only in production
        if IS_PRODUCTION:
            csp_directives.append("upgrade-insecure-requests")

        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Clickjacking protection
        response.headers["X-Frame-Options"] = "SAMEORIGIN"

        # XSS Protection (legacy, but still useful for older browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer Policy: Don't leak referrer to cross-origin requests
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Prevent other origins from loading this origin's resources
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"

        # Permissions Policy: Restrict browser features
        permissions = [
            "accelerometer=()",
            "camera=()",
            "geolocation=()",
            "gyroscope=()",
            "magnetometer=()",
            "microphone=()",
            "payment=(self)",
            "usb=()",
        ]
        response.headers["Permissions-Policy"] = ", ".join(permissions)

        return response
