# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

import hmac
import json
import secrets
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from uuid import uuid4

from shared.service_client import ServiceClient
from database.services.license_provider import license_provider
from database.services.email_service import email_service
from license.billing_provider import billing_provider
from database.core.dependencies import (get_room_service,
                                        get_token_service, get_user_service)
from database.models.user import ConnectionLog, User
from database.schema.password import (ChangePasswordRequest,
                                      ForgotPasswordRequest,
                                      ResetPasswordRequest)
from database.schema.user import UserCreate, UserResponse, UserUpdate
from database.services.room_service import RoomService
from database.services.token_service import JWTService, TokenService
from database.services.user_service import UserService
from fastapi import (APIRouter, Cookie, Depends, Header, HTTPException, Query,
                     Request, status)
from utils import get_secret
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from logger import DEBUG, ERROR, INFO, WARNING, logger
from pydantic import BaseModel
from server_service.room.room import stop_viz

from .guest_utils import create_guest_workspace
from database.services.dashboard_service import DashboardService

from server_service.room.room import stop_viz, stop_user_pod

from .rate_limiter import (forgot_password_limiter, guest_session_limiter,
                           login_limiter, resend_verification_limiter,
                           reset_password_limiter, verify_email_limiter)

TEST = get_secret("TEST")

# Auto-confirmed test emails — signups with these addresses skip the
# email-verification step and are immediately usable. Populated via the
# AUTH_TEST_EMAILS env var at server startup (e.g., by `make up-perf`),
# empty in production. Lets automated perf/functional tests complete
# signup without intercepting confirmation emails.
import os as _os
_AUTH_TEST_EMAILS = frozenset(
    e.strip().lower()
    for e in (_os.environ.get("AUTH_TEST_EMAILS") or "").split(",")
    if e.strip()
)

from server_service.bot_detection import is_bot

auth_router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/server/auth/login")

REFRESH_EXPIRE_DAYS = 30
ACCESS_EXPIRE_MIN = 1
LOCAL = get_secret("LOCAL")
ENV = get_secret("ENV")
GCP = get_secret("GCP")

from shared.workspace import workspace_path as _workspace_path, DIVE_PATH


@auth_router.get("/csrf")
async def get_csrf_token(request: Request):
    token = secrets.token_urlsafe(32)
    # Store in cookie instead of IP-based dict to handle LB/Proxies correctly
    response = JSONResponse(content={"csrfToken": token})
    response.set_cookie(
        key="csrf_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="none",
    )
    return response


@auth_router.get("/bootstrap")
async def bootstrap(
    request: Request,
    user_service: UserService = Depends(get_user_service),
    token_service: TokenService = Depends(get_token_service),
):
    # Collapses the cold-start /csrf + /me pair into one origin round-trip.
    # Tolerates unauth: returns user=null instead of 401 so anonymous visitors
    # still receive a CSRF token.
    csrf = secrets.token_urlsafe(32)

    user_payload = None
    try:
        current_user = await get_current_user(request, user_service, token_service)
    except HTTPException:
        current_user = None

    if current_user is not None:
        license_info = await license_provider.get_license_info(str(current_user.id))
        user_out = UserResponse.from_orm(current_user).dict()
        user_out["license"] = license_info["license_name"]
        user_out["license_details"] = license_info
        missing_fields = get_missing_profile_fields(current_user)
        user_payload = {
            **user_out,
            "profile_complete": len(missing_fields) == 0,
            "missing_fields": missing_fields,
        }

    google_auth_client_id = get_secret("GOOGLE_AUTH_API_KEY") or None

    response = JSONResponse(content={
        "csrfToken": csrf,
        "user": user_payload,
        "google_auth_client_id": google_auth_client_id,
    })
    response.set_cookie(
        key="csrf_token",
        value=csrf,
        httponly=True,
        secure=True,
        samesite="none",
    )
    return response


def verify_csrf_token(request: Request, token: str = None):
    if not token:
        logger().logp(WARNING, f"❌ CSRF Check Failed: Token missing from request header. Client IP: {request.client.host}")
        raise HTTPException(status_code=403, detail="CSRF token missing")
    
    # Validate against cookie instead of IP-bound dict
    cookie_token = request.cookies.get("csrf_token")
    
    if not cookie_token:
         logger().logp(WARNING, f"❌ CSRF Check Failed: CSRF cookie missing. Client IP: {request.client.host}")
         raise HTTPException(status_code=403, detail="CSRF cookie missing")

    if not hmac.compare_digest(cookie_token, token):
        logger().logp(WARNING, f"❌ CSRF Check Failed: Token mismatch. Cookie vs Header.")
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


def get_client_info(request: Request, user_agent: Optional[str] = Header(None)) -> Dict:
    return {"client_ip": request.client.host, "user_agent": user_agent}


async def get_current_user(
    request: Request,
    user_service: UserService = Depends(get_user_service),
    token_service: TokenService = Depends(get_token_service),
) -> User:
    auth_header = request.headers.get("Authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    else:
        token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No access token found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = JWTService.decode_access_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user = await user_service.user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_missing_profile_fields(user):
    missing = []
    is_prof = getattr(user, "is_professional", None)

    for name, field in UserUpdate.model_fields.items():
        if name in ("email", "email_verified"):
            continue  # never required as missing
        value = getattr(user, name, None)

        if name in ("enterprise_name", "phone_number"):
            # Only required if is_professional is True or not set
            if is_prof is not False:
                if value is None:
                    missing.append(name)
            continue
        
        # Consent fields must be explicitly True (not just non-None)
        if name in ("accept_cgu", "accept_privacy"):
            if value is not True:
                missing.append(name)
        elif value is None:
            missing.append(name)
    return missing

async def _log_connection(session, user_id: str, ip_address: str, action: str):
    """Record a connection log entry (CPCE Art. L. 34-1 compliance)."""
    try:
        log = ConnectionLog(user_id=user_id, ip_address=ip_address or "unknown", action=action)
        session.add(log)
        await session.flush()
    except Exception as e:
        logger().logp(ERROR, f"Failed to write connection log: {e}")


async def _login_response(user, request, user_agent, token_service, user_service, room_service):
    # ── Phase 1: DB work — gather data, commit, release connection ──
    old_room_token = request.cookies.get("room_token")
    old_room_id = None
    old_owner_id = None
    need_guest_cleanup = False
    need_viz_stop = False

    if old_room_token:
        old_room = await room_service.room_repo.get_by_token(old_room_token)
        if old_room and old_room.owner_id:
            old_owner = await user_service.user_repo.get_by_id(old_room.owner_id)
            if old_owner and hasattr(old_owner, 'is_guest') and old_owner.is_guest:
                need_guest_cleanup = True
            elif old_room.cmd_port is not None:
                old_room_id = str(old_room.id)
                old_owner_id = str(old_room.owner_id)
                need_viz_stop = True
                await room_service.room_repo.update_by_id(
                    old_room.id, host=None, cmd_port=None, viz_port=None
                )
                await room_service.session.commit()

    client_info = get_client_info(request, user_agent)
    refresh_token, access_token = await token_service.issue_token_pair(
        user, client_info["client_ip"], client_info["user_agent"]
    )
    user.last_seen = datetime.utcnow()
    await _log_connection(user_service.session, str(user.id), client_info["client_ip"], "LOGIN")
    await user_service.commit()
    from database.models.room import RoomType
    all_rooms = await room_service.room_repo.get_user_rooms(user.id)
    chat_rooms = [r for r in all_rooms if getattr(r, 'type', RoomType.CHAT) != RoomType.DASHBOARD]
    if not chat_rooms:
        new_room = await room_service.create_room(user.id)
        chat_rooms = [new_room]
    room = chat_rooms[0]
    room_token_value = str(room.token)
    missing_fields = get_missing_profile_fields(user)
    user_response = UserResponse.from_orm(user).dict()

    # ── Phase 2: slow external calls (K8s) — DB session no longer needed ──
    if need_guest_cleanup:
        await cleanup_guest_session(old_room_token, user_service, room_service, token_service)
    elif need_viz_stop and old_room_id:
        from server_service.room.room import _get_pool
        pool = _get_pool()
        await pool.release(old_room_id)
    # ── Phase 3: build response (no DB needed) ──
    response = JSONResponse(
        content={
            "success": True,
            "message": "Logged in",
            "user": user_response,
            "profile_complete": len(missing_fields) == 0,
            "missing_fields": missing_fields,
        }
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="none",
        # domain=".nveil.com" if not LOCAL else None,
        expires=int(TokenService.REFRESH_TOKEN_LIFETIME.total_seconds()),
    )
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="none",
        # domain=".nveil.com" if not LOCAL else None,
        expires=int(TokenService.ACCESS_TOKEN_LIFETIME.total_seconds()),
    )
    response.set_cookie(
        key="room_token",
        value=room_token_value,
        httponly=True,
        secure=True,
        samesite= "none" if ENV != "staging" else "lax",
        # domain=".nveil.com" if not LOCAL else None,
        expires=int(TokenService.ACCESS_TOKEN_LIFETIME.total_seconds()),
    )
    return response

async def _update_user_profile(user_service, user_obj, user_data: UserUpdate):
    fields = {
        "first_name": user_data.first_name,
        "last_name": user_data.last_name,
        "country": user_data.country,
        "profession": user_data.profession,
        "education": user_data.education,
        "is_professional": user_data.is_professional,
        "enterprise_name": user_data.enterprise_name,
        "phone_number": user_data.phone_number,
        "accept_cgu": user_data.accept_cgu,
        "accept_privacy": user_data.accept_privacy,
        "accept_communication": user_data.accept_communication,
    }
    filtered_fields = {k: v for k, v in fields.items() if v is not None}
    await user_service.user_repo.update_by_id(user_obj.id, **filtered_fields)
    await user_service.session.commit()
    return await user_service.user_repo.get_by_id(user_obj.id)

@auth_router.post("/complete-profile", response_model=UserResponse)
async def complete_profile(
    user: UserUpdate,
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service)
):
    # Only allow the logged-in user to update their own profile
    if user.email != current_user.email:
        raise HTTPException(status_code=403, detail="Cannot update another user's profile")
    return await _update_user_profile(user_service, current_user, user)

@auth_router.post("/register", response_model=UserResponse)
async def register(
    user: UserCreate,
    user_service: UserService = Depends(get_user_service),
):
    new_user = await user_service.user_repo.get_by_email(user.email)
    if new_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    created_user = await user_service.create_user(user.name, user.email, user.password)

    if user.email and user.email.lower() in _AUTH_TEST_EMAILS:
        created_user.email_verified = True
        await user_service.user_repo.session.commit()
        logger().logp(INFO, f"🤖 Auto-confirmed test account: {user.email}")

    try:
        await license_provider.on_user_created(str(created_user.id))
    except Exception as e:
        logger().logp(ERROR, f"Failed to run on_user_created for {user.email}: {e}")
    return await _update_user_profile(user_service, created_user, user)


@auth_router.post("/login")
async def login(
    request: Request,
    user_agent: Optional[str] = Header(None),
    form_data: OAuth2PasswordRequestForm = Depends(),
    user_service: UserService = Depends(get_user_service),
    token_service: TokenService = Depends(get_token_service),
    room_service: RoomService = Depends(get_room_service)
):
    # AJOUTER le rate limiting
    login_limiter(request, identifier=form_data.username)
    
    csrf_token = request.headers.get("X-CSRF-Token")
    if csrf_token:
        verify_csrf_token(request, csrf_token)
    
    user = await user_service.authenticate(form_data.username, form_data.password)
    if not user:
        # Log failed login attempt
        client_info = get_client_info(request, user_agent)
        # We can't log user_id because the user wasn't found, but we log the IP
        logger().logp(WARNING, f"Failed login attempt for {form_data.username} from {client_info['client_ip']}")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if user._password and user.email_verified is not True:
        raise HTTPException(status_code=403, detail="Email not verified")

    return await _login_response(user, request, user_agent, token_service, user_service, room_service)



@auth_router.post("/logout")
async def logout(
    request: Request,
    room_token: str = Cookie(None),
    user_service: UserService = Depends(get_user_service),
    room_service: RoomService = Depends(get_room_service),
    token_service: TokenService = Depends(get_token_service),
):
    token = request.cookies.get("access_token")
    refresh_token = request.cookies.get("refresh_token")
    # Phase 1: DB work — gather what we need, commit, release connection
    need_guest_cleanup = False
    need_pod_stop = False
    pod_owner_id = None
    if token:
        try:
            payload = JWTService.decode_access_token(token)
            if refresh_token:
                try:
                    await token_service.revoke_token(refresh_token)
                except Exception:
                    pass
            user_id = payload.get("user_id")
            if user_id:
                user = await user_service.user_repo.get_by_id(user_id)
                if user:
                    await _log_connection(user_service.session, str(user.id), request.client.host, "LOGOUT")
                    await user_service.commit()
                    if user.is_guest and room_token:
                        need_guest_cleanup = True
                    else:
                        need_pod_stop = True
                        pod_owner_id = str(user.id)
                        # Sweep empty chat rooms for this user. Safe here
                        # because the session is being terminated — no
                        # in-flight requests will be racing against the
                        # delete. Skip on guest path (handled elsewhere).
                        try:
                            deleted = await room_service.cleanup_empty_rooms(str(user.id))
                            if deleted:
                                logger().logp(INFO, f"Logout: cleaned {deleted} empty room(s) for {str(user.id)[:8]}")
                        except Exception as e:
                            logger().logp(WARNING, f"Logout: cleanup_empty_rooms failed: {e}")
        except Exception as e:
            logger().error(f"Error during logout: {e}")

    # Phase 2: slow K8s calls — DB session no longer blocking
    if need_guest_cleanup:
        await cleanup_guest_session(room_token, user_service, room_service, token_service)
    elif need_pod_stop and pod_owner_id:
        await stop_user_pod(pod_owner_id)
    # csrf_tokens.pop(request.client.host, None)
    response = JSONResponse(content={"message": "Logged out successfully"})
    response.delete_cookie(
        key="access_token",
        path="/",
        domain=None,
        secure=False,
        httponly=True,
        samesite="strict",
    )
    response.delete_cookie(
        key="refresh_token",
        path="/",
        domain=None,
        secure=False,
        httponly=True,
        samesite="strict",
    )
    response.delete_cookie(
        key="room_token",
        path="/",
        domain=None,
        secure=False,
        httponly=True,
        samesite="strict",
    )
    response.delete_cookie(
        key="room_id",
        path="/",
        domain=None,
        secure=False,
        httponly=True,
        samesite="strict",
    )
    return response


@auth_router.get("/me")
async def who_am_i(request: Request, current_user: User = Depends(get_current_user)):
    license_info = await license_provider.get_license_info(str(current_user.id))
    user_out = UserResponse.from_orm(current_user).dict()
    user_out["license"] = license_info["license_name"]
    user_out["license_details"] = license_info
    missing_fields = get_missing_profile_fields(current_user)
    return {
        **user_out,
        "profile_complete": len(missing_fields) == 0,
        "missing_fields": missing_fields,
    }


@auth_router.post("/refresh")
async def refresh(
    request: Request,
    user_agent: Optional[str] = Header(None),
    token_service: TokenService = Depends(get_token_service),
    user_service: UserService = Depends(get_user_service),
):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token found")
    try:
        client_info = get_client_info(request, user_agent)
        new_refresh_token, new_access_token = await token_service.rotate_token(
            refresh_token, client_info["client_ip"], client_info["user_agent"]
        )
        # compute new access token expiry (UTC epoch seconds) so client can update local expiry
        access_expiry_ts = int((datetime.utcnow() + TokenService.ACCESS_TOKEN_LIFETIME).timestamp())
        response = JSONResponse(content={"message": "Tokens refreshed", "access_token_expiry": access_expiry_ts})
        response.set_cookie(
            key="refresh_token",
            value=new_refresh_token,
            httponly=True,
            secure=True,
            samesite="none",
            # domain=".nveil.com" if not LOCAL else None,
            expires=int(TokenService.REFRESH_TOKEN_LIFETIME.total_seconds()),
        )
        response.set_cookie(
            key="access_token",
            value=new_access_token,
            httponly=True,
            secure=True,
            samesite="none",
            # domain=".nveil.com" if not LOCAL else None,
            expires=int(TokenService.ACCESS_TOKEN_LIFETIME.total_seconds()),
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


@auth_router.post("/logout-all")
async def logout_all(
    current_user: User = Depends(get_current_user),
    token_service: TokenService = Depends(get_token_service),
):
    count = await token_service.revoke_all_user_tokens(current_user.id)
    return {"message": f"Revoked {count} refresh tokens"}

class VerifyEmailRequest(BaseModel):
    email: str
    code: str

class ResendVerificationRequest(BaseModel):
    email: str

@auth_router.post("/verify-email")
async def verify_email(
    http_request: Request,
    request: VerifyEmailRequest,
    user_service: UserService = Depends(get_user_service)
):
    # Ajouter le rate limiting
    verify_email_limiter(http_request, identifier=request.email)
    
    success, error_msg = await user_service.verify_email(request.email, request.code)
    if not success:
        if "wait" in (error_msg or "").lower():
            raise HTTPException(status_code=429, detail=error_msg)
        elif "invalidated" in (error_msg or "").lower():
            raise HTTPException(status_code=410, detail=error_msg)
        raise HTTPException(status_code=400, detail=error_msg or "Invalid code or email")
    return {"message": "Email verified successfully"}

@auth_router.post("/resend-verification")
async def resend_verification(
    http_request: Request,
    request: ResendVerificationRequest,
    user_service: UserService = Depends(get_user_service)
):
    # Rate limit by IP + email to prevent abuse
    resend_verification_limiter(http_request, identifier=request.email)
    
    success = await user_service.resend_verification_code(request.email)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to resend code")
    return {"message": "Verification code sent"}

@auth_router.post("/forgot-password")
async def forgot_password(
    http_request: Request,
    request: ForgotPasswordRequest,
    user_service: UserService = Depends(get_user_service)
):
    # Rate limit by IP + email to prevent email bombing
    forgot_password_limiter(http_request, identifier=request.email)
    
    success = await user_service.send_password_reset_code(request.email)
    
    return {"message": "If an account exists with this email, a reset code has been sent."}

@auth_router.post("/reset-password")
async def reset_password(
    http_request: Request,
    request: ResetPasswordRequest,
    user_service: UserService = Depends(get_user_service),
    token_service: TokenService = Depends(get_token_service)
):
    reset_password_limiter(http_request, identifier=request.email)

    if len(request.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    
    # Récupérer l'utilisateur AVANT le reset pour pouvoir révoquer ses tokens
    user = await user_service.user_repo.get_by_email(request.email)
    
    success, error_msg = await user_service.reset_password_with_code(
        request.email, 
        request.code, 
        request.new_password
    )
    
    if not success:
        if "wait" in (error_msg or "").lower():
            raise HTTPException(status_code=429, detail=error_msg)
        elif "invalidated" in (error_msg or "").lower():
            raise HTTPException(status_code=410, detail=error_msg)
        raise HTTPException(status_code=400, detail=error_msg or "Invalid or expired code")
    
    # AJOUTER: Révoquer toutes les sessions et notifier via WebSocket
    if user:
        await token_service.revoke_all_user_tokens(user.id)
        logger().logp(INFO, f"🔐 All sessions revoked for user {user.email} after password reset")
        
        from websocket_manager import ws_manager
        await ws_manager.broadcast_to_user(str(user.id), {
            "type": "force_logout",
            "reason": "password_changed"
        })
    
    return {"message": "Password reset successfully. You can now log in."}


@auth_router.delete("/delete-account")
async def delete_account(
    request: Request,
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
    room_service: RoomService = Depends(get_room_service),
    token_service: TokenService = Depends(get_token_service),
):
    """Permanently delete the current user's account and all associated data."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if current_user.is_guest:
        raise HTTPException(status_code=403, detail="Guest accounts cannot be deleted this way")

    user_id = str(current_user.id)
    user_email = current_user.email
    user_name = current_user.name or current_user.email

    logger().logp(INFO, f"🗑️ Starting account deletion for {user_email} (id: {user_id[:8]}...)")

    # ── 1. DB phase: collect room IDs for viz cleanup, then delete user ──
    room_ids_to_release = []
    try:
        user_rooms = await room_service.room_repo.get_user_rooms(user_id)
        for room in user_rooms:
            room_ids_to_release.append(str(room.id))
        # Delete all physical files for this user
        user_data_path = Path(DIVE_PATH) / user_id
        if user_data_path.exists():
            shutil.rmtree(user_data_path, ignore_errors=True)
            logger().logp(INFO, f"  ✅ Deleted user data directory: {user_data_path}")
        await room_service.session.commit()
    except Exception as e:
        logger().logp(ERROR, f"  ⚠️ Room/file cleanup error: {e}")

    # ── 2. Delete the user record (CASCADE handles all child records) ──
    try:
        await user_service.user_repo.delete_by_id(user_id)
        await user_service.session.commit()
        logger().logp(INFO, f"  ✅ Deleted user record for {user_email}")
    except Exception as e:
        logger().logp(ERROR, f"  ❌ Failed to delete user record: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete account")

    # ── 3. Slow external calls — DB session no longer needed ──
    # Release viz pods (K8s API calls)
    from server_service.room.room import _get_pool
    pool = _get_pool()
    for rid in room_ids_to_release:
        try:
            await pool.release(rid)
        except Exception:
            pass
    # Kill user's pod entirely
    try:
        await stop_user_pod(user_id)
    except Exception as e:
        logger().logp(ERROR, f"  ⚠️ Pod cleanup error: {e}")

    # Cancel subscriptions via billing provider
    try:
        await billing_provider.on_account_deleted(user_email)
    except Exception as e:
        logger().logp(ERROR, f"Billing cleanup error: {e}")

    # Send confirmation email
    try:
        await email_service.send_account_deleted_email(user_email, user_name)
    except Exception as e:
        logger().logp(ERROR, f"  ⚠️ Failed to send deletion confirmation email: {e}")

    logger().logp(INFO, f"🗑️ Account deletion complete for {user_email}")

    # Clear auth cookies
    response = JSONResponse(content={"message": "Account deleted successfully"})
    for cookie_name in ["access_token", "refresh_token", "room_token", "room_id"]:
        response.delete_cookie(
            key=cookie_name,
            path="/",
            domain=None,
            secure=False,
            httponly=True,
            samesite="strict",
        )
    return response


@auth_router.post("/change-password")
async def change_password(
    request: Request,
    data: ChangePasswordRequest,
    user_agent: Optional[str] = Header(None),
    user_service: UserService = Depends(get_user_service),
    token_service: TokenService = Depends(get_token_service),
    room_service: RoomService = Depends(get_room_service)
):
    user = await user_service.authenticate(data.email, data.current_password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    
    if data.current_password == data.new_password:
        raise HTTPException(status_code=400, detail="New password must be different from current password")
    
    from database.core.security import hash_password
    await user_service.user_repo.update_by_id(
        user.id,
        _password=hash_password(data.new_password),
    )
    await user_service.commit()
    
    # Revoke all existing refresh tokens (invalidate all other sessions)
    revoked_count = await token_service.revoke_all_user_tokens(user.id)
    logger().logp(INFO, f"🔐 {revoked_count} sessions revoked for user {user.email} after password change")
    
    from websocket_manager import ws_manager
    await ws_manager.broadcast_to_user(str(user.id), {
        "type": "force_logout",
        "reason": "password_changed",
        "exclude_current": True
    })
    
    # Issue new tokens for current session
    return await _login_response(user, request, user_agent, token_service, user_service, room_service)


async def _guest_login_response(user, room, request, user_agent, token_service):
    """Generate login response for guest user."""
    client_info = get_client_info(request, user_agent)
    refresh_token, access_token = await token_service.issue_token_pair(
        user, client_info["client_ip"], client_info["user_agent"]
    )
    
    response = JSONResponse(
        content={
            "success": True,
            "message": "Guest session created",
            "user": {
                "name": user.name,
                "email": user.email,
                "is_guest": True,
            },
            "is_guest": True,
        }
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="none",
        expires=int(TokenService.REFRESH_TOKEN_LIFETIME.total_seconds()),
    )
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="none",
        expires=int(TokenService.ACCESS_TOKEN_LIFETIME.total_seconds()),
    )
    response.set_cookie(
        key="room_token",
        value=str(room.token),
        httponly=True,
        secure=True,
        samesite="none" if ENV != "staging" else "lax",
        expires=int(TokenService.ACCESS_TOKEN_LIFETIME.total_seconds()),
    )
    return response


@auth_router.post("/guest")
async def create_guest_session(
    request: Request,
    user_agent: Optional[str] = Header(None),
    user_service: UserService = Depends(get_user_service),
    token_service: TokenService = Depends(get_token_service),
    room_service: RoomService = Depends(get_room_service)
):
    """
    Create a temporary guest user with a pre-loaded sample dataset.
    Guest users can explore the app but cannot upload files or change settings.
    """
    # 1. Block Bots and Crawlers (including curl, wget, etc.)
    if user_agent and is_bot(user_agent):
        logger().logp(WARNING, f"🤖 Bot blocked from creating guest session. UA: {user_agent}")
        # Return 403 Forbidden to be semantically correct.
        # This prevents the frontend from trying to process an invalid session.
        # Note: Since /server/ is Disallowed in robots.txt, compliant bots (Google)
        # shouldn't even reach this point. This catches the non-compliant ones.
        return JSONResponse(
            status_code=403,
            content={"detail": "Bots are not allowed to create guest sessions."}
        )

    # 2. Rate limit guest session creation per IP
    guest_session_limiter(request)

    # 3. Enforce CSRF Token
    # This prevents direct API calls from outside the application (e.g. simple scripts)
    # The frontend always fetches a CSRF token before calling this.
    csrf_token = request.headers.get("X-CSRF-Token")
    verify_csrf_token(request, csrf_token)

    try:
        # Clean up previous session (e.g. old guest → new guest, or logged-in → guest)
        # Phase 1: DB work for cleanup
        old_room_token = request.cookies.get("room_token")
        need_guest_cleanup = False
        need_viz_release = False
        old_room_id_to_release = None

        if old_room_token:
            old_room = await room_service.room_repo.get_by_token(old_room_token)
            if old_room and old_room.owner_id:
                old_owner = await user_service.user_repo.get_by_id(old_room.owner_id)
                if old_owner and hasattr(old_owner, 'is_guest') and old_owner.is_guest:
                    need_guest_cleanup = True
                elif old_room.cmd_port is not None:
                    old_room_id_to_release = str(old_room.id)
                    need_viz_release = True
                    await room_service.room_repo.update_by_id(
                        old_room.id, host=None, cmd_port=None, viz_port=None
                    )
                    await room_service.session.commit()

        # Generate unique guest identifier
        guest_id = str(uuid4())[:8]
        guest_name = f"Guest_{guest_id}"
        guest_email = f"guest_{guest_id}@temp.nveil.local"

        # Create guest user (no password, is_guest=True)
        guest_user = await user_service.user_repo.create(
            name=guest_name,
            email=guest_email,
            _password=None,
            is_guest=True,
            email_verified=True,
        )
        await user_service.session.commit()

        logger().logp(INFO, f"Created guest user: {guest_name}")

        # Create room for guest
        room = await room_service.create_room(guest_user.id)

        # Lightweight workspace: symlinks to shared template (~10ms)
        create_guest_workspace(str(guest_user.id), str(room.id))

        logger().logp(INFO, f"Created guest room with symlinked workspace: {str(room.id)[:8]}")

        # Phase 2: slow K8s cleanup of old session — DB work done
        if need_guest_cleanup:
            await cleanup_guest_session(old_room_token, user_service, room_service, token_service)
        elif need_viz_release and old_room_id_to_release:
            from server_service.room.room import _get_pool
            pool = _get_pool()
            await pool.release(old_room_id_to_release)

        return await _guest_login_response(guest_user, room, request, user_agent, token_service)

    except Exception as e:
        logger().logp(ERROR, f"Failed to create guest session: {e}")
        raise HTTPException(status_code=500, detail="Failed to create guest session")


async def cleanup_guest_session(
    room_token: str,
    user_service: UserService,
    room_service: RoomService,
    token_service: TokenService,
):
    """
    Clean up guest user session: stop viz, delete room data, delete user.
    Called when guest leaves the page.
    """
    try:
        # Phase 1: DB work — gather data, delete user, commit
        room = await room_service.room_repo.get_by_token(room_token)
        if not room:
            return False
        user = await user_service.user_repo.get_by_id(room.owner_id)
        if not user or not user.is_guest:
            return False

        guest_user_id = str(user.id)
        guest_name = user.name
        logger().logp(INFO, f"Cleaning up guest session: {guest_name}")

        # Collect workspace paths to delete (file I/O, fast)
        from sqlalchemy import select as sa_select
        from database.models.room import Room
        session = user_service.session
        owned_rooms = (await session.execute(
            sa_select(Room).where(Room.owner_id == user.id)
        )).scalars().all()
        for r in owned_rooms:
            room_data_path = _workspace_path(str(user.id), str(r.id))
            if room_data_path.exists():
                shutil.rmtree(room_data_path, ignore_errors=True)

        # Delete guest user (CASCADE handles all child records)
        await user_service.user_repo.delete_by_id(user.id)
        await session.commit()

        # Phase 2: slow K8s call — DB session released
        try:
            await stop_user_pod(guest_user_id)
        except Exception as e:
            logger().logp(WARNING, f"Failed to stop user pod during guest cleanup: {e}")

        logger().logp(INFO, f"Guest session cleaned up: {guest_name}")

        return True
    except Exception as e:
        logger().logp(ERROR, f"Error during guest cleanup: {e}")
        return False
