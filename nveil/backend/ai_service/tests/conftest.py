# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Fixtures for ai_service tests."""

import os
import sys

# Add the ai_service directory itself to sys.path so that internal imports
# like `from llm_processing...` and `from viz_file_utils.utils...` work.
_service_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _service_dir not in sys.path:
    sys.path.insert(0, _service_dir)

# Backend dir is needed for `from shared...`, `from testing...` imports
_backend_dir = os.path.abspath(os.path.join(_service_dir, ".."))
if _backend_dir not in sys.path:
    sys.path.append(_backend_dir)

# tools/ dir is needed for `from logger import ...`
_tools_dir = os.path.join(_backend_dir, "tools")
if _tools_dir not in sys.path:
    sys.path.append(_tools_dir)

