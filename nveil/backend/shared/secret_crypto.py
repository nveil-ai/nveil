# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Symmetric encryption for per-user secrets stored at rest in DB.

Used to protect user-provided LLM API keys before persisting them.
Master key is read from `APP_ENCRYPTION_KEY` (urlsafe-base64 32-byte
Fernet key). Plaintext never touches disk; logs must filter sensitive
fields independently.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from .secrets import get_secret


def _cipher() -> Fernet:
    key = get_secret("APP_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "APP_ENCRYPTION_KEY is not set. Generate one with: "
            "python -c \"import os, base64; "
            "print(base64.urlsafe_b64encode(os.urandom(32)).decode())\""
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secret(plaintext: str) -> str:
    return _cipher().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _cipher().decrypt(ciphertext.encode()).decode()
    except InvalidToken as e:
        raise ValueError(
            "Cannot decrypt secret — APP_ENCRYPTION_KEY changed or data corrupted"
        ) from e


def mask(secret: str, suffix: int = 4) -> str:
    if not secret:
        return ""
    s = secret.strip()
    if len(s) <= suffix:
        return "*" * len(s)
    return f"{'*' * 8}{s[-suffix:]}"
