# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Append-only error logger for AI-generated XML parsing failures.

Writes to debug log files (LOCAL mode only) so that recurring error
patterns can be spotted across requests without digging through
container logs.  Each entry is timestamped and categorised.
"""

from datetime import datetime, timezone
from .config import (
    LOCAL,
    CHOREGRAPH_ERRORS_DEBUG_PATH,
    VISUSPEC_ERRORS_DEBUG_PATH,
)


def _append_entry(path: str, entry: str) -> None:
    """Append a single log entry to *path*, silently ignoring failures."""
    if not LOCAL:
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        pass  # Debug logging must never break the main flow


def log_visuspec_error(
    errors: list[str] | str,
    attempt: int | None = None,
    room_id: str | None = None,
) -> None:
    """Append a VisuSpec (specifications.xml) validation error."""
    if isinstance(errors, str):
        errors = [errors]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    header = f"[{ts}]"
    if room_id:
        header += f" room={room_id}"
    if attempt is not None:
        header += f" attempt={attempt}"
    lines = "\n".join(f"  - {e}" for e in errors)
    _append_entry(VISUSPEC_ERRORS_DEBUG_PATH, f"{header}\n{lines}\n\n")


def log_choregraph_error(
    error: str,
    error_type: str = "unknown",
    attempt: int | None = None,
    room_id: str | None = None,
) -> None:
    """Append a Choregraph (choregraph.xml) generation/validation error."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    header = f"[{ts}]"
    if room_id:
        header += f" room={room_id}"
    if attempt is not None:
        header += f" attempt={attempt}"
    header += f" type={error_type}"
    _append_entry(CHOREGRAPH_ERRORS_DEBUG_PATH, f"{header}\n  {error}\n\n")
