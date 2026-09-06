import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from supabase import AuthApiError, Client, create_client

from auth import get_current_user

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
ALLOWED_SUPABASE_USER_ID = os.environ.get("ALLOWED_SUPABASE_USER_ID")

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL environment variable is not set")
if not SUPABASE_ANON_KEY:
    raise RuntimeError("SUPABASE_ANON_KEY environment variable is not set")
if not ALLOWED_SUPABASE_USER_ID:
    raise RuntimeError("ALLOWED_SUPABASE_USER_ID environment variable is not set")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

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
async def read_me(user: dict = Depends(get_current_user)):
    return {"user_id": user["sub"], "email": user["email"]}

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
