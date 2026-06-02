# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Decoding for SDK request payloads.

The SDK sends request payloads as base64-encoded JSON. The server
decodes them here before forwarding to the AI service.
"""

import base64
import json


def decrypt_engine_blob(blob_b64: str) -> dict:
    """Decode a base64-encoded blob from the SDK.

    Args:
        blob_b64: Base64-encoded JSON blob from SDK request.

    Returns:
        Dict with the decoded payload (e.g. choregraph_xml, catalogue_stats).
    """
    return json.loads(base64.b64decode(blob_b64))
