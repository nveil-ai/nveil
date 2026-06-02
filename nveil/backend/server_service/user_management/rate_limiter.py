# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Simple in-memory rate limiter for sensitive endpoints.
Limits requests per IP address within a sliding time window.
"""
import os
import time
from collections import defaultdict
from threading import Lock
from typing import Dict, List, Tuple

from fastapi import HTTPException, Request
from logger import WARNING, logger


# Addresses in this allowlist are never rate-limited. Populated from the
# AUTH_TEST_EMAILS env var at import time (same var authentification.py uses
# for auto-confirming signup). Empty in production; set by `make up-perf`
# so automated perf tests can signup → login → feature-use → delete repeatedly
# without tripping login/registration/reset limiters.
_AUTH_TEST_EMAILS = frozenset(
    e.strip().lower()
    for e in (os.environ.get("AUTH_TEST_EMAILS") or "").split(",")
    if e.strip()
)


def _is_bypass_identifier(identifier) -> bool:
    """Identifier is typically an email (login_limiter, verify_email_limiter).
    If it matches the AUTH_TEST_EMAILS allowlist, skip rate limiting entirely."""
    if not identifier or not _AUTH_TEST_EMAILS:
        return False
    return str(identifier).strip().lower() in _AUTH_TEST_EMAILS


class RateLimiter:
    """
    Thread-safe in-memory rate limiter using sliding window.
    
    Args:
        max_requests: Maximum number of requests allowed in the window
        window_seconds: Time window in seconds
        block_seconds: How long to block after limit exceeded (0 = just reject)
    """
    
    def __init__(self, max_requests: int = 5, window_seconds: int = 300, block_seconds: int = 600):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.block_seconds = block_seconds
        self._requests: Dict[str, List[float]] = defaultdict(list)
        self._blocked: Dict[str, float] = {}  # IP -> blocked_until timestamp
        self._lock = Lock()
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract real client IP, considering proxies."""
        # Check X-Forwarded-For header (set by load balancers/proxies)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Take the first IP in the chain (original client)
            return forwarded.split(",")[0].strip()
        
        # Check X-Real-IP (common alternative)
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        
        # Fall back to direct client IP
        return request.client.host if request.client else "unknown"
    
    def _cleanup_old_requests(self, key: str, current_time: float):
        """Remove requests outside the sliding window."""
        cutoff = current_time - self.window_seconds
        self._requests[key] = [t for t in self._requests[key] if t > cutoff]
    
    def check(self, request: Request, identifier: str = None) -> Tuple[bool, int]:
        """
        Check if request is allowed.
        
        Args:
            request: FastAPI Request object
            identifier: Optional additional identifier (e.g., email) to rate limit by
        
        Returns:
            Tuple of (allowed: bool, retry_after_seconds: int)
        """
        current_time = time.time()
        client_ip = self._get_client_ip(request)
        
        # Combine IP with identifier if provided (e.g., "192.168.1.1:user@example.com")
        key = f"{client_ip}:{identifier}" if identifier else client_ip
        
        with self._lock:
            # Check if currently blocked
            if key in self._blocked:
                blocked_until = self._blocked[key]
                if current_time < blocked_until:
                    retry_after = int(blocked_until - current_time)
                    return False, retry_after
                else:
                    # Block expired, remove it
                    del self._blocked[key]
            
            # Cleanup old requests
            self._cleanup_old_requests(key, current_time)
            
            # Check rate limit
            if len(self._requests[key]) >= self.max_requests:
                # Block the client
                if self.block_seconds > 0:
                    self._blocked[key] = current_time + self.block_seconds
                    retry_after = self.block_seconds
                else:
                    # Just calculate when oldest request will expire
                    oldest = min(self._requests[key])
                    retry_after = int((oldest + self.window_seconds) - current_time) + 1
                
                return False, retry_after
            
            # Allow request and record it
            self._requests[key].append(current_time)
            return True, 0
    
    def __call__(self, request: Request, identifier: str = None):
        """Callable interface for use as a dependency."""
        # Bypass rate limiting for test-bot accounts (AUTH_TEST_EMAILS env).
        # Production has empty allowlist, so this is a no-op for real traffic.
        if _is_bypass_identifier(identifier):
            return
        allowed, retry_after = self.check(request, identifier)
        if not allowed:
            client_ip = self._get_client_ip(request)
            logger().logp(
                WARNING,
                f"⚠️ Rate limit exceeded for {client_ip} (identifier: {identifier}). "
                f"Retry after {retry_after}s"
            )
            raise HTTPException(
                status_code=429,
                detail=f"Too many requests. Please try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)}
            )


# Pre-configured rate limiters for different use cases

# Forgot password: 3 requests per 5 minutes, block for 10 minutes if exceeded
forgot_password_limiter = RateLimiter(max_requests=3, window_seconds=300, block_seconds=600)

# Resend verification: 3 requests per 5 minutes, block for 10 minutes if exceeded
resend_verification_limiter = RateLimiter(max_requests=3, window_seconds=300, block_seconds=600)

# Login attempts: 5 attempts per 5 minutes, block for 15 minutes if exceeded
login_limiter = RateLimiter(max_requests=10, window_seconds=300, block_seconds=900)

# Registration: 3 registrations per hour per IP
registration_limiter = RateLimiter(max_requests=3, window_seconds=3600, block_seconds=3600)

# Password reset verification: 5 attempts per 5 minutes, block for 10 minutes
# CRITICAL for brute-force protection on OTP
reset_password_limiter = RateLimiter(max_requests=5, window_seconds=300, block_seconds=600)

# Email verification: 5 attempts per 5 minutes, block for 10 minutes
verify_email_limiter = RateLimiter(max_requests=5, window_seconds=300, block_seconds=600)

# Guest session creation: 5 per 10 minutes per IP, block for 30 minutes
guest_session_limiter = RateLimiter(max_requests=5, window_seconds=600, block_seconds=1800)
