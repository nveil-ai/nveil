# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

# /workspaces/app/nveil/backend/server_service/oauth_provider.py

from datetime import datetime, timedelta

import jwt
from database.core.dependencies import get_user_service
from database.models import user as UserModel
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from user_management.authentification import get_current_user
from utils import get_secret

OAUTH_SECRET = get_secret("OAUTH_SECRET")
OAUTH_ALGORITHM = "HS256"
OAUTH_CLIENT_ID = "fider-client-id"
OAUTH_REDIRECT_URIS = [
    "https://feedback.nveil.com/oauth/_ligqf6fykb/callback",
    "https://app.nveil.com/oauth/callback"
]

router = APIRouter()
auth_codes = {}

def generate_code_for_user(user_id):
    code = f"code-{user_id}-{datetime.utcnow().timestamp()}"
    auth_codes[code] = user_id
    return code

def get_current_user_from_cookie(request: Request):
    # Use your existing session/cookie logic
    # For FastAPI, you might use Depends(get_current_user)
    # Here, we just return None for demo
    return None

@router.get("/authorize")
async def authorize(request: Request, client_id: str, redirect_uri: str, state: str = None, current_user: UserModel = Depends(get_current_user)):
    # Validate client_id and redirect_uri
    if client_id != OAUTH_CLIENT_ID or redirect_uri not in OAUTH_REDIRECT_URIS:
        raise HTTPException(status_code=400, detail="Invalid client_id or redirect_uri")
    # If user is not logged in, redirect to login page
    if not current_user:
        login_url = f"https://app.nveil.com/login?next={request.url.path}"
        return RedirectResponse(login_url)
    # If logged in, auto-approve and generate code
    code = generate_code_for_user(current_user.id)
    redirect_url = f"{redirect_uri}?code={code}&state={state or ''}"
    return RedirectResponse(redirect_url)

@router.post("/token")
async def token(grant_type: str = Form(...), code: str = Form(None), client_id: str = Form(...), redirect_uri: str = Form(...)):
    if grant_type != "authorization_code":
        raise HTTPException(status_code=400, detail="Unsupported grant_type")
    if client_id != OAUTH_CLIENT_ID or redirect_uri not in OAUTH_REDIRECT_URIS:
        raise HTTPException(status_code=400, detail="Invalid client_id or redirect_uri")
    user_id = auth_codes.get(code)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid code")
    # Issue JWT access_token
    access_token = jwt.encode(
        {"sub": user_id, "exp": datetime.utcnow() + timedelta(hours=1)},
        OAUTH_SECRET,
        algorithm=OAUTH_ALGORITHM
    )
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.get("/userinfo", response_model=None)
async def userinfo(token = Depends(OAuth2PasswordBearer(tokenUrl="/oauth/token")), user_service = Depends(get_user_service)):
    try:
        payload = jwt.decode(token, OAUTH_SECRET, algorithms=[OAUTH_ALGORITHM])
        user_id = payload.get("sub")
        user = await user_service.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return JSONResponse({
            "id": user.id,
            "name": f"{user.first_name} {user.last_name}",
            "email": user.email
        })
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid token")