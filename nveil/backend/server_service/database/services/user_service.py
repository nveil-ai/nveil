# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

from datetime import datetime
from typing import List, Optional, Tuple

from ..core.security import hash_password, verify_password
from ..models.user import User
from ..repository.user_repository import UserRepository
from .base import BaseService

class	UserService(BaseService):
    def __init__(self, session, email_service=None):
        super().__init__(session)
        if email_service is not None:
            self.email_service = email_service
        else:
            from .email_service import email_service as _default_email
            self.email_service = _default_email

    @property
    def	user_repo(self) -> UserRepository:
        return self.get_repo(UserRepository, User)

    async def	create_user(self, name: str, email: str, password: str) -> User:
        user = None

        existing_email = await self.user_repo.get_by_email(email)
        if existing_email:
            raise ValueError(f"Email '{email}' already registered")

        auto_verify = not self.email_service.is_available

        if password:
            password_hash = hash_password(password)
            user = await self.user_repo.create(
                name=name,
                email=email,
                _password=password_hash,
                email_verified=auto_verify
            )
        else:
            user = await self.user_repo.create(
                name=name,
                email=email,
                _password=None,
                email_verified=True
            )
        await self.user_repo.session.commit()

        if self.email_service.is_available:
            if password:
                code = self.email_service.generate_code(str(user.id))
                await self.email_service.send_verification_email(email, code, name)
            else:
                await self.email_service.send_welcome_email(email, name)

        return user

    async def verify_email(self, email: str, code: str) -> Tuple[bool, Optional[str]]:
        """
        Verify email with the provided code.

        Returns:
            Tuple of (success, error_message)
        """
        user = await self.user_repo.get_by_email(email)
        if not user:
            return False, "Invalid email address"

        if user.email_verified:
            return True, None

        success, error_msg = self.email_service.verify_code(str(user.id), code)
        if not success:
            return False, error_msg

        user.email_verified = True
        await self.user_repo.session.commit()

        if self.email_service.is_available:
            await self.email_service.send_welcome_email(email, user.name)

        return True, None

    async def resend_verification_code(self, email: str) -> Tuple[bool, Optional[str]]:
        """
        Resend verification code with rate limiting.

        Returns:
            Tuple of (success, error_message)
        """
        if not self.email_service.is_available:
            return False, "Email service not configured"

        user = await self.user_repo.get_by_email(email)
        if not user or user.email_verified:
            return False, "Invalid request"

        can_regenerate, wait_time = self.email_service.can_regenerate_code(str(user.id))
        if not can_regenerate:
            return False, f"Please wait {wait_time} seconds before requesting a new code."

        code = self.email_service.generate_code(str(user.id))
        await self.email_service.send_verification_email(email, code, user.name)
        return True, None

    async def	authenticate(self, email: str, password: str) -> Optional[User]:
        """Authenticate a user by email and password."""
        user = await self.user_repo.get_by_email(email)
        if not user:
            return None
        # Check if user has a password (not OAuth-only user)
        if not user._password:
            return None
        if not verify_password(password, user._password):
            return None
        return user

    async def	set_online_status(self, user_id: str, is_online: bool) -> bool:
        update_data = {
            "is_online": is_online,
            "last_seen": datetime.now()
        }
        res = await self.user_repo.update_by_id(user_id, **update_data)
        await self.user_repo.session.commit()
        return res

    async def search_users(self, query: str) -> List[User]:
        return await self.user_repo.search_by_email(query)

    async def get_user_settings(self, user_id: str) -> dict:
        user = await self.user_repo.get_by_id(user_id)
        settings = {}
        if user:
            settings["accept_communication"] = user.accept_communication
        
        return settings
    
    async def update_user_settings(self, user_id: str, settings: dict) -> bool:
        update_data = {}
        if "accept_communication" in settings:
            update_data["accept_communication"] = settings["accept_communication"]
        
        if update_data:
            res = await self.user_repo.update_by_id(user_id, **update_data)
            await self.user_repo.session.commit()
            return res
        return False

    async def send_password_reset_code(self, email: str) -> bool:
        if not self.email_service.is_available:
            return False

        user = await self.user_repo.get_by_email(email)
        if not user:
            return False

        code = self.email_service.generate_code(str(user.id))

        result = await self.email_service.send_password_reset_email(email, code, user.name)
        return result is not None

    async def reset_password_with_code(self, email: str, code: str, new_password: str) -> Tuple[bool, Optional[str]]:
        user = await self.user_repo.get_by_email(email)
        if not user:
            return False
        
        # Use protected verification
        success, error_msg = self.email_service.verify_code(str(user.id), code)
        if not success:
            return False, error_msg

        # Mettre à jour le mot de passe
        from database.core.security import hash_password
        await self.user_repo.update_by_id(
            user.id,
            _password=hash_password(new_password),
            email_verified=True  # L'email est vérifié puisqu'ils ont reçu le code
        )
        await self.session.commit()
        return True, None

