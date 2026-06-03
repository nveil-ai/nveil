# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Public API route for SDK specification generation.

Single endpoint — ``POST /api/v1/sdk/process`` — polymorphic on whether
the request carries a ``session_id``:

* No ``session_id`` → fresh turn. The SDK sends a base64-encoded blob
  containing ``choregraph_xml`` + ``catalogue_stats``. The graph pauses
  at the choregraph interrupt and returns ``{status: "awaiting_choregraph",
  session_id, choregraph_xml, visualization_plan}``.
* ``session_id`` present → resume. The SDK sends a base64-encoded
  blob containing post-transform ``choregraph_xml``, ``specifications_xml``
  and ``catalogue_stats``. The graph finishes and returns
  ``{status: "complete", visuspec_xml, explanation, warnings}``.

Mirrors the ``chat_endpoint`` (web) ``arun`` / ``aresume`` dispatch shape.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from shared.engine_crypto import decrypt_engine_blob
from shared.service_client import ServiceClient
from user_management.api_auth import require_scope
from user_management.rate_limiter import RateLimiter
from utils import get_secret

log = logging.getLogger(__name__)

API_VERSION = "0.1.0"

# Schema version negotiation
MIN_CLIENT_SCHEMA_VERSION = "0.1.0"
CURRENT_SCHEMA_VERSION = "1.0.0"

# API throttling — per API key, not per IP.
# processing_plan + visualization_generate together count as one "generation".
# Default: 5 generations per minute (10 requests), block for 2 minutes if exceeded.
_api_throttle = RateLimiter(max_requests=10, window_seconds=60, block_seconds=120)

router = APIRouter()


def _check_schema_version(request: Request) -> None:
    """Validate the SDK schema version from request headers."""
    client_version = request.headers.get("X-Nveil-Schema-Version", "")
    if not client_version:
        return
    try:
        client_parts = [int(x) for x in client_version.split(".")]
        min_parts = [int(x) for x in MIN_CLIENT_SCHEMA_VERSION.split(".")]
    except (ValueError, IndexError):
        return
    if client_parts < min_parts:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "sdk_upgrade_required",
                "min_version": MIN_CLIENT_SCHEMA_VERSION,
                "message": f"Your SDK version ({client_version}) is too old. "
                           f"Run: pip install --upgrade nveil",
            },
        )


def _check_throttle(request: Request, api_key) -> None:
    """Enforce per-API-key rate limiting."""
    _api_throttle(request, identifier=str(api_key.id))


def _decrypt_request_blob(payload: dict, blob_key: str = "request_blob") -> dict:
    """Decode the base64-encoded request blob and merge into payload."""
    if blob_key not in payload:
        raise HTTPException(
            status_code=400,
            detail="Missing request_blob in payload. Use the NVEIL SDK to send requests.",
        )
    decrypted = decrypt_engine_blob(payload[blob_key])
    del payload[blob_key]
    payload.update(decrypted)
    return payload


AI_HOST = get_secret("AI_HOST", "localhost")
AI_PORT = int(get_secret("AI_PORT", "8100"))

_ai_client = ServiceClient(verify=True)


def _ai_url(path: str) -> str:
    return f"https://{AI_HOST}:{AI_PORT}{path}"


@router.post("/sdk/process")
async def sdk_process(
    request: Request,
    auth: tuple = Depends(require_scope("visualization:generate")),
):
    """Unified SDK endpoint — fresh call or resume depending on ``session_id``.

    The SDK sends a base64-encoded blob; this route decodes it,
    attaches the authenticated ``owner_id``, and forwards to the AI
    service. On the final ``complete`` response we increment the API
    key's generation counter.
    """
    _check_schema_version(request)
    user, api_key = auth
    _check_throttle(request, api_key)
    payload = await request.json()
    payload["owner_id"] = str(user.id)

    payload = _decrypt_request_blob(payload)

    # The LLM provider/credentials are fixed server-side at setup time
    # (operator .env); ai_service runs every request on its boot-selected
    # default provider. The SDK cannot override it — no LLM headers are
    # accepted or forwarded.
    resp = await _ai_client.post(
        _ai_url("/ai/sdk/process"),
        json=payload,
        timeout=120.0,
    )

    if resp.status_code and resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.data)

    # Count one generation per completed two-step flow (on the resume response).
    if isinstance(resp.data, dict) and resp.data.get("status") == "complete":
        from database.services.api_key_service import ApiKeyService
        from database.core.database import db
        try:
            async with db.session() as session:
                svc = ApiKeyService(session)
                await svc.increment_generations(api_key.id)
        except Exception:
            pass

    return JSONResponse(
        content=resp.data,
        status_code=resp.status_code or 200,
        headers={"X-Nveil-Schema-Version": CURRENT_SCHEMA_VERSION},
    )
