import os
from dataclasses import dataclass

from dotenv import load_dotenv
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

load_dotenv()

SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET")
if not SUPABASE_JWT_SECRET:
    raise RuntimeError("SUPABASE_JWT_SECRET environment variable is not set")

ALLOWED_SUPABASE_USER_ID = os.environ.get("ALLOWED_SUPABASE_USER_ID")
if not ALLOWED_SUPABASE_USER_ID:
    raise RuntimeError("ALLOWED_SUPABASE_USER_ID environment variable is not set")

# auto_error=False so we raise our own 401 with a consistent detail message.
bearer_scheme = HTTPBearer(
    scheme_name="Supabase access token",
    description="Paste the access_token returned by POST /api/v1/auth/login.",
    auto_error=False,
)


@dataclass
class AuthenticatedUser:
    id: str
    email: str
    access_token: str


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> AuthenticatedUser:
    unauthorized_headers = {"WWW-Authenticate": "Bearer"}

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401, detail="Missing or malformed token", headers=unauthorized_headers
        )

    token = credentials.credentials.strip()
    try:
        payload = jwt.decode(
            token, SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated"
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=401, detail="Invalid or expired token", headers=unauthorized_headers
        ) from exc

    if not payload.get("sub") or not payload.get("email"):
        raise HTTPException(
            status_code=401,
            detail="Token missing required claims",
            headers=unauthorized_headers,
        )

    # Mirrors the check /api/v1/auth/login does at sign-in time. Without it, anyone who
    # obtains a validly-signed Supabase token by some other route (e.g. self-serve signup
    # left enabled on the Supabase project) would still pass every protected endpoint here.
    if payload["sub"] != ALLOWED_SUPABASE_USER_ID:
        raise HTTPException(status_code=403, detail="Account is not authorized")

    return AuthenticatedUser(id=payload["sub"], email=payload["email"], access_token=token)
