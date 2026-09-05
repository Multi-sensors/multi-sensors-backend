# Auth API Design

> Status: spec. Only `GET /api/v1/me` on an HS256 shared secret exists today; the `/auth`
> prefix, JWKS verification, login and reset described below are not built yet.

## 1. Architecture decision

- **Email + password, single account.** No signup.
- **Supabase Auth owns** credential verification, token issuance, refresh/rotation, and
  password updates. **The frontend never calls Supabase auth methods directly:** login and
  reset go through FastAPI; `supabase-js` only *holds* the session.
- **FastAPI owns** the auth contract, JWT verification, and the sole-user check: `sub` must
  equal `ALLOWED_SUPABASE_USER_ID` (exact UUID match).

```
Frontend  --(email/password)-->  FastAPI  --> Supabase Auth
Frontend  <--(access + refresh token)--  FastAPI   (403 if not the sole user)
Frontend  --> supabase.auth.setSession(...)        (supabase-js handles refresh)
Frontend  --(Authorization: Bearer <access token>)-->  FastAPI protected routes
```

## 2. Endpoints

All under `/api/v1/auth`. Passwords are held in memory only — never logged or persisted.

### `POST /auth/login`

Request `{ "email": "owner@example.com", "password": "<password>" }`; **200 OK** returns the
Supabase session, passed straight to `supabase.auth.setSession()`:

```json
{
  "access_token": "<supabase-access-token>",
  "refresh_token": "<supabase-refresh-token>",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": { "id": "<supabase-user-uuid>", "email": "owner@example.com" }
}
```

`401` on bad credentials, `403` if the account is not `ALLOWED_SUPABASE_USER_ID`.

### `GET /auth/me`

Send `Authorization: Bearer <access-token>`. Returns minimal identity only — no raw JWT,
no extra claims: `{ "id": "<supabase-user-uuid>", "email": "owner@example.com" }`

### `POST /auth/reset-password`

Authenticated password change: `Authorization: Bearer <current-access-token>` plus
`{ "new_password": "...", "confirm_password": "..." }`. Returns **204 No Content** with an
empty body; the update uses the caller's own access token, never the service-role key, and
is rate limited. Afterwards the frontend confirms success, re-checks `/auth/me`, and
continues to the dashboard — or clears state and returns to login if Supabase invalidated
the session.

## 3. Error contract

| Condition | Status | Public response |
| --- | --- | --- |
| Invalid login credentials | 401 | Invalid email or password |
| Missing / malformed bearer token | 401 | Authentication required |
| Invalid or expired access token | 401 | Invalid or expired session |
| Authenticated but unapproved user | 403 | Account is not authorized |
| Password mismatch or policy violation | 400 | Passwords do not match / generic policy message |

Every bearer-auth 401 includes `WWW-Authenticate: Bearer`. Logs may carry a sanitized error
category and correlation ID — never credentials, tokens, or sensitive claims.

## 4. Token verification

One shared dependency (`require_sole_user`) guards every protected route. It verifies the
JWT against Supabase's JWKS (`<SUPABASE_URL>/auth/v1/.well-known/jwks.json`) using only the
configured asymmetric algorithm — never the one from the token header — and checks `iss`
(`<SUPABASE_URL>/auth/v1`), `aud`, `exp`, `sub`; keys are cached briefly and refetched on an
unknown `kid`. Swagger's **Authorize** button takes the *access* token, never the refresh one.

## 5. Note to frontend

Login: submit to `POST /auth/login`, hand both tokens to `supabase.auth.setSession()`, then
call `GET /auth/me`. Render protected content only after `/auth/me` succeeds, never while
session restore is in flight; on any auth failure, clear protected state and return to login.
Sign-out is `supabase.auth.signOut()` + clearing client state; no logout route, no custom refresh.

## 6. Configuration

```
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_PUBLISHABLE_KEY=<publishable-key>
SUPABASE_JWT_AUDIENCE=authenticated
ALLOWED_SUPABASE_USER_ID=<sole-user-uuid>
FRONTEND_ORIGIN=https://<application-domain>
```

No service-role key, secret key, or legacy JWT secret in backend or frontend code. Every
user-owned table carries `owner_id uuid NOT NULL REFERENCES auth.users(id)` with RLS scoped
by `owner_id = auth.uid()`; forward the user's access token on data calls so RLS applies —
defense in depth, not a replacement for the sole-user check.
