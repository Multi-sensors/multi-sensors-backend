# Auth API Design

## 1. Architecture decision

- **Auth method:** email + password.
- **Frontend talks to Supabase Auth directly.** The backend never sees raw credentials.
  Login, signup, and password reset are Supabase client calls made from the frontend —
  they are not backend routes.
- **Backend responsibility:** verify the Supabase-issued JWT on incoming requests and
  gate protected routes. No password handling, no server-side session store.
- **Sessions:** short-lived access token + refresh token, both issued and rotated by
  Supabase (`supabase-js` handles rotation automatically on the frontend). The backend
  verifies the access token per-request and is stateless.
- **Users:** known research-team members only. Self-serve signup is out of scope unless
  the team decides otherwise later.

```
Frontend  --(email/password)-->  Supabase Auth
Frontend  <--(access + refresh JWT)--  Supabase Auth
Frontend  --(Authorization: Bearer <access JWT>)-->  FastAPI backend
FastAPI backend  --(verify JWT signature/claims only, no call to Supabase)-->  200 / 401
```

## 2. Backend contract

### `GET /api/v1/me`

Proves token verification works end-to-end and serves as the template for future
protected routes.

**Request**

```
GET /api/v1/me
Authorization: Bearer <supabase-access-token>
```

**Response — 200 OK**

```json
{
  "user_id": "auth0-style-uuid-from-sub-claim",
  "email": "person@example.com"
}
```

**Response — 401 Unauthorized**

Returned when the `Authorization` header is missing, malformed, or the token fails
signature/expiry/audience verification. No other backend route requires auth yet.

## 3. Note to frontend

The backend does **not** expose login, signup, or reset-password endpoints — call
Supabase directly from the frontend using `supabase-js`:

- `supabase.auth.signInWithPassword({ email, password })` — login
- `supabase.auth.resetPasswordForEmail(email, { redirectTo })` — password reset request
- `supabase.auth.signUp({ email, password })` — only if/when self-serve signup is turned on (currently out of scope)

After login, pass the session's `access_token` as a `Bearer` token to any backend route
under `/api/v1/`. The only such route today is `GET /api/v1/me`.

Once you build the reset-password page, send its URL to Daksha/Stephanie so it can be
set as the redirect target in Supabase's password-reset email template.
