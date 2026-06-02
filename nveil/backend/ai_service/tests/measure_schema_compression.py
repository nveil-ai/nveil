# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Standalone script measuring token savings from XSD → YAML conversion.

Usage:
    python measure_schema_compression.py
"""

import re
import sys
import tempfile
from pathlib import Path

# Direct import to avoid ai_service __init__.py chain
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "llm_processing"))
from xsd_to_yaml import convert_xsd_to_yaml


def _find_xsd(relative_path: str) -> Path:
    """Resolve XSD path in both local dev and Docker container layouts."""
    # Try relative to repo root (local dev)
    repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    local = repo_root / relative_path
    if local.exists():
        return local
    # Docker container: choregraph/ at /choregraph
    container = Path("/") / relative_path
    if container.exists():
        return container
    # Devcontainer / baked-in image layout
    devcontainer = Path("/workspaces/app") / relative_path
    if devcontainer.exists():
        return devcontainer
    raise FileNotFoundError(
        f"Cannot find {relative_path} in any known layout "
        f"(tried {local}, {container}, {devcontainer})"
    )


VISUSPEC_PATH = _find_xsd("dive/VisuSpec.xsd")
TRANSFORMGRAPH_PATH = _find_xsd("choregraph/src/choregraph/TransformGraph.xsd")


def measure(name: str, xsd_path: Path) -> None:
    xsd_raw = xsd_path.read_text(encoding="utf-8")
    # Strip TODO comments (same regex as prompt.py)
    cleaned = re.sub(r"<!--TODO\s*:.*?-->", "", xsd_raw, flags=re.DOTALL)
    yaml_out = convert_xsd_to_yaml(cleaned)

    xsd_chars = len(cleaned)
    yaml_chars = len(yaml_out)
    xsd_tokens = xsd_chars // 4
    yaml_tokens = yaml_chars // 4
    reduction_pct = 100 - yaml_chars * 100 / xsd_chars

    print(f"\n{'=' * 60}")
    print(f"  {name}")
    print(f"{'=' * 60}")
    print(f"  XSD (cleaned):  {xsd_chars:>8,} chars  (~{xsd_tokens:,} tokens)")
    print(f"  YAML output:    {yaml_chars:>8,} chars  (~{yaml_tokens:,} tokens)")
    print(f"  Reduction:      {reduction_pct:>7.1f}%")
    print(f"  Tokens saved:   ~{xsd_tokens - yaml_tokens:,}")

    # Write YAML to temp file for inspection
    tmp = Path(tempfile.gettempdir()) / f"{name.replace(' ', '_').lower()}.yaml"
    tmp.write_text(yaml_out, encoding="utf-8")
    print(f"  YAML written:   {tmp}")


if __name__ == "__main__":
    measure("VisuSpec", VISUSPEC_PATH)
    measure("TransformGraph", TRANSFORMGRAPH_PATH)
    print()
