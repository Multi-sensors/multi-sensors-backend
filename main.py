import os

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Response
from pydantic import BaseModel
from supabase import AuthApiError, Client, create_client

from auth import ALLOWED_SUPABASE_USER_ID, AuthenticatedUser, get_current_user

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
# Not required yet: Supabase falls back to the redirect configured in its own Reset
# Password email template until the frontend's reset-password page URL is finalized.
FRONTEND_RESET_PASSWORD_URL = os.environ.get("FRONTEND_RESET_PASSWORD_URL")

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL environment variable is not set")
if not SUPABASE_ANON_KEY:
    raise RuntimeError("SUPABASE_ANON_KEY environment variable is not set")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
SUPABASE_AUTH_URL = f"{SUPABASE_URL}/auth/v1"


def _supabase_auth_headers(access_token: str) -> dict:
    return {"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {access_token}"}

app = FastAPI(
    title="Multi-Sensors Backend",
    version="0.1.0",
    description=(
        "Log in via **POST /api/v1/auth/login**, copy the `access_token` from the "
        "response, then click **Authorize** and paste it to call protected endpoints."
    ),
)


class LoginRequest(BaseModel):
    email: str
    password: str

    model_config = {
        "json_schema_extra": {
            "example": {"email": "person@example.com", "password": "hunter2"}
        }
    }


class LoginUser(BaseModel):
    id: str
    email: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: LoginUser


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirm(BaseModel):
    new_password: str
    confirm_password: str


@app.get('/')
async def index():
    return {"hello": "world"}

@app.get('/about')
async def about():
    return "Multi sensor research project backend"

@app.get('/health')
async def health():
    return {"status": "ok"}

@app.get(
    '/api/v1/me',
    tags=["auth"],
    summary="Current user",
    responses={401: {"description": "Missing, malformed, or expired token"}},
)
async def read_me(user: AuthenticatedUser = Depends(get_current_user)):
    return {"user_id": user.id, "email": user.email}

@app.post(
    '/api/v1/auth/login',
    tags=["auth"],
    summary="Login",
    response_model=LoginResponse,
    responses={
        401: {"description": "Invalid email or password"},
        403: {"description": "Account is not authorized"},
    },
)
async def login(credentials: LoginRequest):
    try:
        result = supabase.auth.sign_in_with_password(
            {"email": credentials.email, "password": credentials.password}
        )
    except AuthApiError as exc:
        raise HTTPException(status_code=401, detail="Invalid email or password") from exc

    if result.session is None or result.user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if result.user.id != ALLOWED_SUPABASE_USER_ID:
        # Credentials were valid, so Supabase issued a session. Discard it rather than
        # leaving another account's session on the shared client.
        try:
            supabase.auth.sign_out()
        except AuthApiError:
            pass
        raise HTTPException(status_code=403, detail="Account is not authorized")

    return {
        "access_token": result.session.access_token,
        "refresh_token": result.session.refresh_token,
        "token_type": "bearer",
        "expires_in": result.session.expires_in,
        "user": {
            "id": result.user.id,
            "email": result.user.email
        }
    }

@app.post(
    '/api/v1/auth/logout',
    tags=["auth"],
    status_code=204,
    summary="Logout",
    responses={401: {"description": "Missing, malformed, or expired token"}},
)
async def logout(user: AuthenticatedUser = Depends(get_current_user)):
    try:
        response = httpx.post(
            f"{SUPABASE_AUTH_URL}/logout",
            params={"scope": "local"},
            headers=_supabase_auth_headers(user.access_token),
            timeout=10,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Failed to revoke session") from exc
    return Response(status_code=204)

@app.post(
    '/api/v1/auth/password-reset/request',
    tags=["auth"],
    status_code=202,
    summary="Request a password reset email",
)
async def request_password_reset(body: PasswordResetRequest):
    options = (
        {"redirect_to": FRONTEND_RESET_PASSWORD_URL} if FRONTEND_RESET_PASSWORD_URL else None
    )
    try:
        supabase.auth.reset_password_for_email(body.email, options=options)
    except AuthApiError:
        # Never reveal whether the email is registered.
        pass
    return {"detail": "If that email is registered, a password reset link has been sent."}

@app.post(
    '/api/v1/auth/password-reset/confirm',
    tags=["auth"],
    status_code=204,
    summary="Change password (authenticated)",
    responses={
        400: {"description": "Passwords do not match, or do not meet Supabase's policy"},
        401: {"description": "Missing, malformed, or expired token"},
    },
)
async def confirm_password_reset(
    body: PasswordResetConfirm, user: AuthenticatedUser = Depends(get_current_user)
):
    if body.new_password != body.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    response = httpx.put(
        f"{SUPABASE_AUTH_URL}/user",
        json={"password": body.new_password},
        headers=_supabase_auth_headers(user.access_token),
        timeout=10,
    )
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail="Password does not meet policy requirements")

    return Response(status_code=204)
