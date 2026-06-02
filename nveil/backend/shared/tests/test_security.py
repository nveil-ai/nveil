# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for shared.security — path validation and filename sanitization.

Security-critical: these functions prevent directory traversal attacks.
All tests use real filesystem paths via tmp_path — no mocks.
"""

import pytest
from pathlib import Path

from shared.security import (
    safe_path,
    sanitize_filename,
    sanitize_file_path,
    sanitize_owner_and_room_id,
)


class TestSafePath:
    def test_relative_path_within_base(self, tmp_path):
        result = safe_path(tmp_path, "subdir/file.txt")
        assert result == (tmp_path / "subdir" / "file.txt").resolve()

    def test_simple_filename(self, tmp_path):
        result = safe_path(tmp_path, "data.csv")
        assert result == (tmp_path / "data.csv").resolve()

    def test_rejects_parent_traversal(self, tmp_path):
        with pytest.raises(ValueError, match="outside the allowed directory"):
            safe_path(tmp_path, "../../../etc/passwd")

    def test_rejects_absolute_outside_base(self, tmp_path):
        with pytest.raises(ValueError, match="outside the allowed directory"):
            safe_path(tmp_path, "/etc/passwd")

    def test_accepts_absolute_inside_base(self, tmp_path):
        inner = tmp_path / "allowed" / "file.txt"
        result = safe_path(tmp_path, str(inner))
        assert result == inner.resolve()

    def test_resolves_dot_segments(self, tmp_path):
        result = safe_path(tmp_path, "a/b/../c/file.txt")
        assert result == (tmp_path / "a" / "c" / "file.txt").resolve()

    def test_rejects_dot_dot_escaping_base(self, tmp_path):
        (tmp_path / "a").mkdir()
        with pytest.raises(ValueError):
            safe_path(tmp_path / "a", "../secret.txt")


class TestSanitizeFilename:
    def test_normal_filename(self):
        assert sanitize_filename("data.csv") == "data.csv"

    def test_strips_path_components(self):
        assert sanitize_filename("../../etc/passwd") == "passwd"

    def test_strips_path_with_slashes(self):
        assert sanitize_filename("/root/secret/file.txt") == "file.txt"

    def test_removes_special_chars(self):
        result = sanitize_filename("my file (1).csv")
        assert " " not in result
        assert "(" not in result
        assert ")" not in result

    def test_preserves_dots_dashes_underscores(self):
        assert sanitize_filename("my-file_v2.csv") == "my-file_v2.csv"

    def test_empty_after_sanitize(self):
        result = sanitize_filename("///")
        assert result == ""

    def test_unicode_stripped(self):
        result = sanitize_filename("données.csv")
        # Only alnum + . - _ survive
        assert all(c.isalnum() or c in (".", "-", "_") for c in result)


class TestSanitizeFilePath:
    def test_path_within_base(self, tmp_path):
        (tmp_path / "data").mkdir()
        target = tmp_path / "data" / "file.csv"
        target.touch()
        result = sanitize_file_path(str(target), tmp_path)
        assert result == target.resolve()

    def test_rejects_path_outside_base(self, tmp_path):
        with pytest.raises(ValueError, match="outside the allowed directory"):
            sanitize_file_path("/etc/passwd", tmp_path)


class TestSanitizeOwnerAndRoomId:
    def test_valid_uuids(self):
        o, r = sanitize_owner_and_room_id(
            "550e8400-e29b-41d4-a716-446655440000",
            "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        )
        assert o  # not empty
        assert r  # not empty

    def test_strips_path_traversal_from_owner(self):
        o, r = sanitize_owner_and_room_id("../../etc", "room-id")
        # Path components stripped, only "etc" survives
        assert o == "etc"
        assert ".." not in o

    def test_rejects_empty_after_sanitize(self):
        with pytest.raises(ValueError, match="Invalid"):
            sanitize_owner_and_room_id("///", "room-id")

    def test_strips_dangerous_chars(self):
        o, r = sanitize_owner_and_room_id("owner<script>", "room;drop")
        # Angle brackets and semicolons stripped
        assert "<" not in o
        assert ";" not in r
