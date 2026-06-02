# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for shared.security — path sanitization and validation."""

import pytest
from pathlib import Path

from shared.security import safe_path, sanitize_filename, sanitize_file_path, sanitize_owner_and_room_id


class TestSafePath:
    def test_relative_within_base(self, tmp_path):
        (tmp_path / "subdir").mkdir()
        result = safe_path(str(tmp_path), "subdir")
        assert result == (tmp_path / "subdir").resolve()

    def test_absolute_within_base(self, tmp_path):
        child = tmp_path / "file.txt"
        child.touch()
        result = safe_path(str(tmp_path), str(child))
        assert result == child.resolve()

    def test_traversal_raises(self, tmp_path):
        with pytest.raises(ValueError, match="outside"):
            safe_path(str(tmp_path), "../../../etc/passwd")

    def test_dot_dot_in_middle_raises(self, tmp_path):
        (tmp_path / "a").mkdir()
        with pytest.raises(ValueError, match="outside"):
            safe_path(str(tmp_path), "a/../../etc/passwd")


class TestSanitizeFilename:
    def test_strips_path_components(self):
        assert sanitize_filename("/some/path/file.txt") == "file.txt"

    def test_removes_special_chars(self):
        result = sanitize_filename("file<>:name?.txt")
        # Only alphanumeric, dot, hyphen, underscore survive
        assert all(c.isalnum() or c in ".-_" for c in result)
        assert "file" in result
        assert ".txt" in result

    def test_simple_name_unchanged(self):
        assert sanitize_filename("data-file_v2.csv") == "data-file_v2.csv"


class TestSanitizeFilePath:
    def test_valid_path(self, tmp_path):
        child = tmp_path / "data.csv"
        child.touch()
        result = sanitize_file_path(str(child), str(tmp_path))
        assert result == child.resolve()

    def test_traversal_raises(self, tmp_path):
        with pytest.raises(ValueError):
            sanitize_file_path(str(tmp_path / ".." / "escape"), str(tmp_path))


class TestSanitizeOwnerAndRoomId:
    def test_valid_ids(self):
        owner, room = sanitize_owner_and_room_id("owner123", "room-456")
        assert owner == "owner123"
        assert room == "room-456"

    def test_empty_owner_raises(self):
        with pytest.raises(ValueError):
            sanitize_owner_and_room_id("", "room-456")

    def test_empty_room_raises(self):
        with pytest.raises(ValueError):
            sanitize_owner_and_room_id("owner123", "")
