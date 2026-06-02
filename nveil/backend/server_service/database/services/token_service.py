# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

import hashlib
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

import jwt
from dotenv import load_dotenv
from fastapi import HTTPException, status
from logger import ERROR, logger

from ..models.refresh_token import RefreshToken
from ..models.user import User
from ..repository.refresh_token_repository import RefreshTokenRepository
from ..repository.user_repository import UserRepository
from .base import BaseService
from utils import get_secret

class   JWTService:
    SECRET_KEY = get_secret("SECRET_KEY")
    ALGORITHM = get_secret("ALGORITHM", default="HS256")
    @classmethod
    def create_access_token(cls, payload: Dict) -> str:
        to_encode = payload.copy()
        if isinstance(to_encode.get('exp'), datetime):
            to_encode['exp'] = int(to_encode['exp'].timestamp())
        if isinstance(to_encode.get('iat'), datetime):
            to_encode['iat'] = int(to_encode['iat'].timestamp())
        encoded_jwt = jwt.encode(to_encode, cls.SECRET_KEY, algorithm=cls.ALGORITHM)
        return encoded_jwt
    
    @classmethod
    def decode_access_token(cls, token: str) -> Optional[Dict]:
        try:
            payload = jwt.decode(token, cls.SECRET_KEY, algorithms=[cls.ALGORITHM])
            return payload
        except jwt.exceptions.InvalidTokenError:
            return None
        except Exception as e:
            logger().logp(ERROR, f"JWT decode error: {e}")
            return None

class	TokenService(BaseService):
    ACCESS_TOKEN_LIFETIME:       timedelta = timedelta(minutes=15)
    REFRESH_TOKEN_LIFETIME:      timedelta = timedelta(days=30)
    TOKEN_BYTE_LENGTH:           int = 32
    REUSE_DETECTION_ENABLED:     bool = True
    MAX_ACTIVE_TOKENS_PER_USER:  int = 5
    
    @property
    def token_repo(self) -> RefreshTokenRepository:
        return self.get_repo(RefreshTokenRepository, RefreshToken)

    @property
    def user_repo(self) -> UserRepository:
        return self.get_repo(UserRepository, User)

    def _generate_token(self) -> str:
        return secrets.token_urlsafe(self.TOKEN_BYTE_LENGTH)
    
    def _hash_token(self, token: str) -> str:
        return hashlib.sha512(token.encode()).hexdigest()

    def _create_access_token_payload(self, user: User) -> Dict:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return {
            "user_id": str(user.id),
            "email": user.email,
            "name": user.name,
            "type": "access",
            "iat": now,
            "exp": now + self.ACCESS_TOKEN_LIFETIME,
        }

    async def   issue_token_pair(self, user: User, client_ip: Optional[str] = None,
                                user_agent: Optional[str] = None, token_family_id: Optional[str] = None
                                ) -> Tuple[str, str]:
        active_tokens = await self.token_repo.find_active_by_user(user.id)
        if len(active_tokens) >= self.MAX_ACTIVE_TOKENS_PER_USER:
            oldest = min(active_tokens, key=lambda t: t.created_at)
            oldest.is_revoked = True
        if token_family_id is None:
            token_family_id = uuid.uuid4()
        
        refresh_token_plain = self._generate_token()
        refresh_token_hash = self._hash_token(refresh_token_plain)
        refresh_token = RefreshToken(
            token_hash=refresh_token_hash,
            token_family_id=token_family_id,
            user_id=user.id,
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + self.REFRESH_TOKEN_LIFETIME,
            used_at=datetime.now(timezone.utc).replace(tzinfo=None),
            client_ip=client_ip,
            user_agent=user_agent
        )
        await self.token_repo.create(refresh_token)
        access_token_payload = self._create_access_token_payload(user)
        access_token_jwt = JWTService.create_access_token(access_token_payload)
        await self.token_repo.session.commit()
        return refresh_token_plain, access_token_jwt

    async def rotate_token(self, refresh_token_plain: str, client_ip: Optional[str] = None,
                            user_agent: Optional[str] = None) -> Tuple[str, str]:
        token_hash = self._hash_token(refresh_token_plain)
        token = await self.token_repo.find_by_token_hash(token_hash)
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")        
        if self.REUSE_DETECTION_ENABLED and token.is_used:
            await self.token_repo.revoke_family(token.token_family_id)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token reuse detected. Please re-authenticate.")
        if token.is_revoked:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has been revoked")
        if token.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has expired")
        await self.token_repo.mark_as_used(token)
        user = await self.user_repo.get_by_id(token.user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        new_refresh_token, new_access_token_jwt = await self.issue_token_pair(
            user=user,
            client_ip=client_ip,
            user_agent=user_agent,
            token_family_id=token.token_family_id
        )
        await self.token_repo.session.commit()
        return new_refresh_token, new_access_token_jwt

    async def   revoke_token(self, refresh_token_plain: str) -> bool:
        token_hash = self._hash_token(refresh_token_plain)
        token = await self.token_repo.find_by_token_hash(token_hash)
        if not token:
            return False
        token.is_revoked = True
        await self.token_repo.session.commit()
        return True

    async def   revoke_all_user_tokens(self, user_id: str) -> int:
        res = await self.token_repo.revoke_user_tokens(user_id)
        await self.token_repo.session.commit()
        return res
    
    async def   validate_and_decode_token(self, refresh_token_plain: str) -> Optional[RefreshToken]:
        token_hash = self._hash_token(refresh_token_plain)
        token = await self.token_repo.find_by_token_hash(token_hash)
        if not token or token.is_revoked or token.expires_at <datetime.datetime.now(timezone.utc).replace(tzinfo=None):
            return None
        return token
