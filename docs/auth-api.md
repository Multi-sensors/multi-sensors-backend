# Auth API Design

> Status: built. Login, logout, `GET /api/v1/me`, and both password-reset endpoints exist
> and are tested. Verification is still an HS256 shared secret (`SUPABASE_JWT_SECRET`), not
> the JWKS scheme described in §4 — that remains a future upgrade, not yet built.

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

Auth endpoints live under `/api/v1/auth`; the identity check is `/api/v1/me` (no `/auth`
prefix — predates the rest of this design, kept as-is rather than churn a working route).
Passwords are held in memory only — never logged or persisted.

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

### `GET /api/v1/me`

Send `Authorization: Bearer <access-token>`. Returns minimal identity only — no raw JWT,
no extra claims: `{ "user_id": "<supabase-user-uuid>", "email": "owner@example.com" }`

### `POST /auth/logout`

`Authorization: Bearer <access-token>`, no body. Revokes that session server-side (scope
`local` — only the presented session, not every device) via Supabase's own `/auth/v1/logout`,
forwarding the caller's own access token — never the service-role key. Returns **204 No
Content**. `401` if the token is missing/invalid, `502` if Supabase's own endpoint fails.
The frontend should still call `supabase.auth.signOut()` (or just clear local session state)
after this succeeds — this endpoint's job is revoking the token server-side, not managing
client state.

### `POST /auth/password-reset/request`

Unauthenticated. Body `{ "email": "..." }`. Forwards to Supabase's password-recovery email
(equivalent of `resetPasswordForEmail`), using `FRONTEND_RESET_PASSWORD_URL` as the redirect
if configured. **Always returns 202** with a generic message regardless of whether the email
is registered — never leaks account existence via status code or timing-sensitive branching.

### `POST /auth/password-reset/confirm`

Authenticated password change: `Authorization: Bearer <current-access-token>` plus
`{ "new_password": "...", "confirm_password": "..." }`. Returns **204 No Content** with an
empty body; the update uses the caller's own access token, never the service-role key.
`400` on a client-side mismatch between the two fields, or if Supabase itself rejects the
new password (e.g. policy violation). Afterwards the frontend confirms success, re-checks
`/api/v1/me`, and continues to the dashboard — or clears state and returns to login if
Supabase invalidated the session.

## 3. Error contract

| Condition | Status | Public response |
| --- | --- | --- |
| Invalid login credentials | 401 | Invalid email or password |
| Missing / malformed bearer token | 401 | Missing or malformed token |
| Invalid or expired access token | 401 | Invalid or expired token |
| Authenticated but unapproved user | 403 | Account is not authorized |
| Password mismatch or policy violation | 400 | Passwords do not match / Password does not meet policy requirements |
| Supabase's own logout call fails | 502 | Failed to revoke session |

Every bearer-auth 401 includes `WWW-Authenticate: Bearer`. Logs may carry a sanitized error
category and correlation ID — never credentials, tokens, or sensitive claims.

## 4. Token verification

One shared dependency, `get_current_user` (`auth.py`), guards every protected route
(`/api/v1/me`, `/auth/logout`, `/auth/password-reset/confirm`). Today it verifies the JWT
signature against the **HS256 shared secret** (`SUPABASE_JWT_SECRET`), checks `aud` ==
`authenticated`, requires `sub`/`email` claims to be present, and — the sole-user check —
requires `sub == ALLOWED_SUPABASE_USER_ID`, 403 otherwise. This is the same check `/auth/login`
does at sign-in; centralizing it here means a token obtained by any other route (e.g. if
self-serve signup were ever left on in Supabase) still can't reach a protected endpoint.
**Not yet built:** migrating to JWKS-based asymmetric verification (`<SUPABASE_URL>/auth/v1/.well-known/jwks.json`)
instead of the shared secret — tracked as a future upgrade, not required for the current
single-user threat model. Swagger's **Authorize** button takes the *access* token, never the
refresh one. Every 401 from this dependency includes `WWW-Authenticate: Bearer`.

## 5. Note to frontend

Login: submit to `POST /auth/login`, hand both tokens to `supabase.auth.setSession()`, then
call `GET /api/v1/me`. Render protected content only after that call succeeds, never while
session restore is in flight; on any auth failure, clear protected state and return to login.

Sign-out: call `POST /auth/logout` (revokes the session server-side), then still run
`supabase.auth.signOut()` / clear local client state regardless of that call's outcome —
don't leave stale tokens in the browser just because the server-side revoke had a hiccup.

Forgot password: `POST /auth/password-reset/request` with just an email — always returns 202,
don't build a "check your email" UI that branches on the response differing by whether the
account exists. In-app change-password (user is already logged in): `POST
/auth/password-reset/confirm` with the current access token plus the new password twice.

## 6. Configuration

```
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_ANON_KEY=<anon/publishable key>
SUPABASE_JWT_SECRET=<Project Settings -> API -> JWT Settings>
ALLOWED_SUPABASE_USER_ID=<sole-user-uuid>
FRONTEND_RESET_PASSWORD_URL=<optional, frontend's reset-password page>
```

No service-role key in backend or frontend code — `SUPABASE_ANON_KEY` plus the caller's own
access token is enough for every endpoint here, including logout and password reset.
`SUPABASE_JWT_SECRET` (HS256 shared secret) is used today per §4; moving to JWKS would drop
that env var in favor of fetching public keys from Supabase directly. Every user-owned table
should carry `owner_id uuid NOT NULL REFERENCES auth.users(id)` with RLS scoped by
`owner_id = auth.uid()`; forward the user's access token on data calls so RLS applies —
defense in depth, not a replacement for the sole-user check.
