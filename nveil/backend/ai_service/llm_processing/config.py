# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Centralized configuration for the AI service LLM processing pipeline.

Paths shared with other services (DIVE_PATH, workspace helpers) come from
``shared.workspace``.  This module adds AI-service-specific constants that
have no business living in the shared layer.
"""

import os

from dive.xml import get_xsd_path
from dotenv import load_dotenv

load_dotenv()

# --- Environment flags ---
# LOCAL toggles local-dev shortcuts (e.g. debug error logs). Exported for
# debug_errors. It no longer drives any path: the dev-container notion is gone
# (code always lives at /nveil/backend in the image), so paths are absolute.
LOCAL = os.getenv("LOCAL") == "1"

# --- VisuSpec XSD path (bundled inside the dive package) ---
XSD_FILEPATH = str(get_xsd_path())

# --- AI-service file paths ---
FAQ_FILEPATH = "/nveil/backend/ai_service/faq_nveil.txt"
PROMPT_TEMPLATES_PATH = "/nveil/backend/ai_service/llm_processing/prompt_templates.yaml"
TRANSFORMATION_FUNCTIONS_CATALOGUE_PATH = (
    "/choregraph/src/choregraph/transformation_functions_catalogue.json"
)

# --- Server connectivity ---
SERVER_HOST = os.getenv("SERVER_HOST") or "localhost"
SERVER_PORT = 8000

# --- Feature flags ---
USE_YAML_SCHEMA = os.getenv("USE_YAML_SCHEMA", "1") == "1"

# --- Debug output paths (auto-generated YAML schemas) ---
VISUSPEC_YAML_DEBUG_PATH = "/nveil/backend/ai_service/llm_processing/visuspec_schema.debug.yaml"
CHOREGRAPH_YAML_DEBUG_PATH = "/nveil/backend/ai_service/llm_processing/choregraph_schema.debug.yaml"

# --- Debug error logs (append-mode, local only) ---
VISUSPEC_ERRORS_DEBUG_PATH = "/nveil/backend/ai_service/llm_processing/visuspec_errors.debug.log"
CHOREGRAPH_ERRORS_DEBUG_PATH = "/nveil/backend/ai_service/llm_processing/choregraph_errors.debug.log"
