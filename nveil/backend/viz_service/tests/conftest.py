# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Fixtures for viz_service tests."""

import os
import sys

# Force all VTK render windows offscreen from creation — prevents the brief
# native window flash on Windows when vtkRenderWindow() is instantiated.
os.environ.setdefault("VTK_DEFAULT_RENDER_WINDOW_OFFSCREEN", "1")

# viz_renderer/ is the actual Python root for viz_service
_viz_renderer_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "viz_renderer")
)
_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_tools_dir = os.path.join(_backend_dir, "tools")

if _viz_renderer_dir not in sys.path:
    sys.path.insert(0, _viz_renderer_dir)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)
if _tools_dir not in sys.path:
    sys.path.append(_tools_dir)
