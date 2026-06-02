# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for database.core.security — bcrypt password hashing."""

from database.core.security import hash_password, verify_password


class TestHashPassword:
    def test_returns_string(self):
        result = hash_password("my_password")
        assert isinstance(result, str)

    def test_returns_bcrypt_format(self):
        result = hash_password("my_password")
        assert result.startswith("$2b$")

    def test_different_salts(self):
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        assert h1 != h2  # different salts each time


class TestVerifyPassword:
    def test_correct_password(self):
        hashed = hash_password("correct_password")
        assert verify_password("correct_password", hashed) is True

    def test_incorrect_password(self):
        hashed = hash_password("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_empty_string_password(self):
        hashed = hash_password("")
        assert verify_password("", hashed) is True
        assert verify_password("notempty", hashed) is False

    def test_roundtrip(self):
        for pw in ["short", "a" * 72, "spëcial-çhars!", "  spaces  "]:
            hashed = hash_password(pw)
            assert verify_password(pw, hashed) is True
