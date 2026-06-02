# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

import time
import threading
from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict

from logger import INFO, logger


class EmailProvider(ABC):
    """Interface for transactional email delivery.

    Subclass this to integrate your own email service (SMTP, SendGrid, etc.).
    See plugins/README.md for a full example.
    """

    @property
    def is_available(self) -> bool:
        return True

    @abstractmethod
    def generate_code(self, user_id: str, timestamp: float = None) -> str: ...

    @abstractmethod
    def verify_code(self, user_id: str, code: str) -> Tuple[bool, Optional[str]]: ...

    @abstractmethod
    def can_regenerate_code(self, user_id: str) -> Tuple[bool, int]: ...

    @abstractmethod
    async def send_verification_email(
        self, to_email: str, code: str, user_name: str
    ) -> Optional[object]: ...

    @abstractmethod
    async def send_password_reset_email(
        self, to_email: str, code: str, user_name: str
    ) -> Optional[object]: ...

    @abstractmethod
    async def send_welcome_email(
        self, to_email: str, user_name: str
    ) -> Optional[object]: ...

    @abstractmethod
    async def send_license_subscription_email(
        self, to_email: str, user_name: str, license_name: str, period: str
    ) -> Optional[object]: ...

    @abstractmethod
    async def send_account_deleted_email(
        self, to_email: str, user_name: str
    ) -> Optional[object]: ...


class OTPAttemptTracker:
    """Tracks OTP verification attempts per user to prevent brute-force attacks."""

    def __init__(self, max_attempts: int = 5, lockout_seconds: int = 300):
        self.max_attempts = max_attempts
        self.lockout_seconds = lockout_seconds
        self._attempts: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def check_and_record_attempt(self, user_id: str) -> Tuple[bool, int, str]:
        current_time = time.time()

        with self._lock:
            if user_id in self._attempts:
                data = self._attempts[user_id]
                if current_time - data.get('first_attempt_time', 0) > self.lockout_seconds:
                    del self._attempts[user_id]

            if user_id not in self._attempts:
                self._attempts[user_id] = {
                    'attempts': 1,
                    'first_attempt_time': current_time,
                    'last_attempt_time': current_time
                }
                return True, 0, ""

            data = self._attempts[user_id]

            if data['attempts'] >= self.max_attempts:
                return False, self.lockout_seconds, "Maximum attempts exceeded. Please request a new code."

            delay = 2 ** (data['attempts'] - 1)
            time_since_last = current_time - data.get('last_attempt_time', 0)

            if time_since_last < delay:
                wait_time = int(delay - time_since_last) + 1
                return False, wait_time, f"Please wait {wait_time} seconds before trying again."

            data['attempts'] += 1
            data['last_attempt_time'] = current_time

            return True, 0, ""

    def clear_attempts(self, user_id: str) -> None:
        with self._lock:
            self._attempts.pop(user_id, None)

    def is_locked(self, user_id: str) -> bool:
        with self._lock:
            if user_id not in self._attempts:
                return False
            return self._attempts[user_id]['attempts'] >= self.max_attempts


class LogOnlyEmail(EmailProvider):
    """Community default: no email provider configured."""

    @property
    def is_available(self) -> bool:
        return False

    def generate_code(self, user_id: str, timestamp: float = None) -> str:
        return "000000"

    def verify_code(self, user_id: str, code: str):
        return code == "000000", None

    def can_regenerate_code(self, user_id: str):
        return True, 0

    async def send_verification_email(self, to_email, code, user_name):
        pass

    async def send_password_reset_email(self, to_email, code, user_name):
        pass

    async def send_welcome_email(self, to_email, user_name):
        pass

    async def send_license_subscription_email(self, to_email, user_name, license_name, period):
        pass

    async def send_account_deleted_email(self, to_email, user_name):
        pass


try:
    from nveilplugin.email import ResendEmailProvider as _EmailImpl
except ImportError:
    _EmailImpl = LogOnlyEmail

email_service = _EmailImpl()
