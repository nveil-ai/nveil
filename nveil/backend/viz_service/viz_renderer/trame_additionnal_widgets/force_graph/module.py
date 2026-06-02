# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

from pathlib import Path

# Path to the www directory
serve = {"__force_graph": str(Path(__file__).parent / "www")}

# Scripts to load from the www directory and CDNs
scripts = [
    "https://unpkg.com/force-graph",
    "https://unpkg.com/3d-force-graph",
    "__force_graph/index.js",
]

# No vue_template needed here, component is registered in index.js
vue_template = None
