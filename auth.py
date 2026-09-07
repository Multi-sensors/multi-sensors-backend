import os

from dotenv import load_dotenv
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

load_dotenv()

SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET")
if not SUPABASE_JWT_SECRET:
    raise RuntimeError("SUPABASE_JWT_SECRET environment variable is not set")

# auto_error=False so we raise our own 401 with a consistent detail message.
bearer_scheme = HTTPBearer(
    scheme_name="Supabase access token",
    description="Paste the access_token returned by POST /api/v1/auth/login.",
    auto_error=False,
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing or malformed token")

    token = credentials.credentials.strip()
    try:
        payload = jwt.decode(
            token, SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated"
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    if not payload.get("sub") or not payload.get("email"):
        raise HTTPException(status_code=401, detail="Token missing required claims")

    return payload
