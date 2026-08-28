# Authentication & Tenant Authorization

Replaces the platform-wide `API_SHARED_SECRET` (API_FORENSICS.md Section 1
— "No Real Auth; Shared Secret Is Exposed Client-Side").

## What runs

- Real per-user login: `POST /auth/login` with `{email, password}` (bcrypt-hashed
  passwords, see `app/core/security.py`). Rate-limited at the strict tier
  (`5/minute`, `app/core/rate_limit.py`) to blunt credential stuffing.
- Sessions are opaque tokens stored in Redis (`session:<token>` -> `{user_id,
  email}`, TTL `SESSION_TTL_SECONDS`, default 4 hours) — reuses the existing
  Redis instance rather than adding a new session store. The token is handed
  to the browser as an **httpOnly** cookie (`orm_session`), so client-side JS
  can never read it — the exact class of exposure `NEXT_PUBLIC_API_SHARED_SECRET`
  had.
- `POST /auth/logout` deletes the Redis key immediately (real revocation,
  unlike a stateless JWT).
- `GET /auth/me` returns the current user plus the `client_id`s they're
  granted — used by the dashboard both to check auth state and to populate
  the tenant dropdown.
- Every router except `/health`, `/metrics`, and `/auth/*` itself requires
  `get_current_user` (`app/core/auth.py`) — a valid, non-expired session.
- Every endpoint that takes a `client_id` (path, query, or body field) is
  additionally scoped by `require_client_access` / `user_has_client_access`,
  checked against the `user_client_access` table. A user with no row for a
  given client_id gets `403`, not a silent empty result.

## Tables added

- `users` — `id, email (unique), password_hash, is_active, created_at`
- `user_client_access` — `id, user_id, client_id, created_at`, unique on
  `(user_id, client_id)`. No implicit access: a user with zero rows here can
  see zero clients.

See `database/migrations/0001_add_auth_tables.sql` for applying this to an
existing database, and `database/schema.sql` (updated) for a fresh bootstrap.

## Provisioning a user

There's no self-service signup (deliberately out of scope — see below).
Create/update a user and grant client access with:

```bash
python scripts/seed_user.py --email you@example.com --password 'change-me' --all-clients
# or grant specific clients:
python scripts/seed_user.py --email you@example.com --password 'change-me' --client-id <uuid>
```

Onboarding a *new* client (`POST /clients/onboard`) automatically grants the
onboarding user access to it.

## Frontend

- `src/app/login/page.tsx` — login form, posts to `/auth/login`.
- `src/middleware.ts` — redirects to `/login` when the `orm_session` cookie
  is absent (presence-only check; real validation is the backend's job on
  every API call).
- `src/lib/api.ts` — every fetch now sends `credentials: "include"` instead
  of an `X-API-Key` header; no shared secret is baked into the build.
- The tenant dropdown (`Sidebar.tsx`) is fed by `GET /clients`, which the
  backend now scopes to the logged-in user's granted clients — no separate
  client-side filtering needed.

## Roles & user management

- Two roles: `super_admin` (sees every client, manages users) and
  `client_user` (scoped to whatever `user_client_access` rows they hold —
  same mechanism as above). `require_super_admin` / `require_client_access`'s
  super_admin bypass live in `app/core/auth.py`.
- No self-service signup and no email/invite flow: a `super_admin` creates
  an account via `POST /admin/users` (email, role, client_id(s)), which
  generates a strong password server-side (`secrets.token_urlsafe`, see
  `app/core/security.py`) and returns it **once** in that response. The
  account is active immediately. The admin hands the password to the user
  out of band (Slack, in person, etc.) — nothing is emailed.
- `POST /admin/users/{id}/reset-password` generates and returns a new
  password the same way, without touching role or client access.
- `GET /admin/users` lists everyone; `DELETE /admin/users/{id}` hard-deletes
  (refuses self-delete and refuses deleting the last remaining
  `super_admin`); `PATCH /admin/users/{id}/clients` replaces a
  `client_user`'s client grants.
- The generated password is never logged or persisted anywhere except as
  its bcrypt hash — only that one API response ever carries the plaintext.

## Local dev / plain-HTTP note

Browsers refuse to send a `Secure` cookie over plain HTTP. `docker-compose.yml`
sets `SESSION_COOKIE_SECURE=false` by default for local review; set it (or
leave it unset, defaulting to `true`) for any real HTTPS deployment.

## Deliberately deferred (follow-ups, not built here)

- SSO / OAuth
- Password-reset-via-email flow
- Email verification
- 2FA
- Per-user rate limiting (`rate_limit.py`'s limiter still keys on IP, not
  the authenticated user — noted as a fast follow-up now that identity
  exists to key on)
