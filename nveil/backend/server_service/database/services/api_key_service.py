# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status

from ..models.api_key import ApiKey
from ..models.user import User
from ..repository.api_key_repository import ApiKeyRepository
from ..repository.user_repository import UserRepository
from .base import BaseService

KEY_PREFIX = "nveil_"
KEY_BYTE_LENGTH = 48


def _hash_key(raw_key: str) -> str:
    """SHA-512 hash of the raw API key. Same pattern as TokenService."""
    return hashlib.sha512(raw_key.encode()).hexdigest()


class ApiKeyService(BaseService):

    @property
    def key_repo(self) -> ApiKeyRepository:
        return self.get_repo(ApiKeyRepository, ApiKey)

    @property
    def user_repo(self) -> UserRepository:
        return self.get_repo(UserRepository, User)

    def _generate_key(self) -> str:
        return KEY_PREFIX + secrets.token_urlsafe(KEY_BYTE_LENGTH)

    async def create_key(
        self,
        user_id: UUID,
        name: str,
        scopes: List[str],
        expires_at: Optional[datetime] = None,
    ) -> Tuple[str, ApiKey]:
        """Create a new API key.

        Returns (plaintext_key, ApiKey). The plaintext key is shown
        **once** at creation — only the SHA-512 hash is stored.
        """
        plaintext_key = self._generate_key()
        key_prefix = plaintext_key[:12]

        api_key = await self.key_repo.create(
            user_id=user_id,
            key_prefix=key_prefix,
            key_hash=_hash_key(plaintext_key),
            name=name,
            scopes=json.dumps(scopes),
            expires_at=expires_at,
        )
        await self.commit()
        return plaintext_key, api_key

    async def validate_key(self, raw_key: str) -> Optional[Tuple[User, ApiKey]]:
        """Validate an API key by hashing and looking up. Returns (User, ApiKey) or None."""
        if not raw_key or not raw_key.startswith(KEY_PREFIX):
            return None

        api_key = await self.key_repo.get_by_hash(_hash_key(raw_key))
        if api_key is None:
            return None

        # Check expiry
        if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
            return None

        # Increment request counter and update last_used
        await self.key_repo.increment_requests(api_key.id)
        await self.commit()

        user = await self.user_repo.get_by_id(str(api_key.user_id))
        if user is None:
            return None

        return user, api_key

    async def list_keys(self, user_id: UUID) -> List[ApiKey]:
        """List all active (non-revoked) keys for a user."""
        return await self.key_repo.get_by_user(user_id)

    async def revoke_key(self, key_id: UUID, user_id: UUID) -> bool:
        """Revoke an API key. Only the owner can revoke."""
        api_key = await self.key_repo.get_by_id(str(key_id))
        if api_key is None or api_key.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found",
            )
        success = await self.key_repo.update_by_id(
            str(key_id),
            is_active=False,
            revoked_at=datetime.now(timezone.utc),
        )
        await self.commit()
        return success

    async def increment_generations(self, key_id: UUID) -> None:
        """Increment the generation counter for a key."""
        await self.key_repo.increment_generations(key_id)
        await self.commit()

    def get_scopes(self, api_key: ApiKey) -> List[str]:
        """Parse the scopes JSON from an ApiKey."""
        return json.loads(api_key.scopes)
