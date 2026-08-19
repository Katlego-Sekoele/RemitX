# Clerk authentication — design

**Date:** 2026-08-19
**Status:** Approved, ready for implementation planning
**Scope:** Auth plumbing only

## Problem

The RemitX brief requires that "a sender registers and logs in" before any
remittance activity, and every later feature — KYC, beneficiaries, wallets,
transaction limits — hangs off a known user identity. Today the API has no
auth of any kind: every endpoint is anonymous, and there is no user table for
domain records to reference.

The frontend has a partial Clerk scaffold (`ClerkProvider` plus unstyled
sign-in buttons in `root.tsx`), and the infrastructure already provisions
Clerk secrets through Key Vault. Neither half is connected to the other.

This design closes that gap: a signed-in browser session produces a verified
caller identity inside FastAPI, backed by a `users` row.

## Scope

**In scope:**

- Clerk-hosted sign-in and sign-up embedded in the SPA
- Protected frontend routes with redirect-back-after-login
- Session token forwarded from the browser to the API
- FastAPI verification of that token, exposing the caller as a `User`
- A `users` table keyed by `clerk_user_id`, populated just-in-time
- Protecting the existing `/integration-messages` endpoints

**Out of scope** (each gets its own spec):

- KYC fields, submission flow, and admin approve/reject
- Transaction limits and tiering
- Profile management UI
- Beneficiaries, wallets, remittances
- Clerk webhooks for user sync
- Admin roles and authorization beyond "is this caller signed in"

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Token verification | Official `clerk-backend-api` SDK | Stays current with Clerk's changes; `authenticate_request()` handles issuer/`azp` validation rather than us reimplementing it |
| Python floor | Bump to 3.11 | SDK requires ≥3.10; 3.11 matches `Dockerfile`'s `python:3.11` exactly, closing the local-vs-production version gap |
| User provisioning | Just-in-time on first authenticated request | No public endpoint, no webhook secret, no tunnel for local dev; the row is guaranteed present before any handler runs |
| Frontend routing | Dedicated `/sign-in`, `/sign-up` + protected layout | Deep-linkable, survives refresh (SWA already rewrites SPA routes), keeps gating in one place |
| Token plumbing | `useApi()` hook returning bound functions | No global mutable state, mockable in tests, composes with TanStack Query's `queryFn` |

### Consequence of the Python bump

`requires-python` moves from `>=3.9` to `>=3.11` and ruff's `target-version`
from `py39` to `py311`. The CLAUDE.md paragraph mandating 3.9-compatible code
is rewritten accordingly; PEP 604 unions (`X | Y`) and `match` become legal.

**Operational note:** the development machine's system Python is 3.9.6. Local
venvs must be rebuilt against a 3.11 interpreter (pyenv or Homebrew) or the
API must be run through Docker Compose, which is already on 3.11. This is a
one-time setup cost and should be called out in the implementation plan.

## API design

### Package layout

Authentication is cross-cutting, so it sits beside the existing four layers
rather than inside one:

```
remitx_api/auth/
  __init__.py
  clerk.py         # token verification against Clerk
  dependencies.py  # FastAPI dependencies exposing the caller
```

### `auth/clerk.py`

Wraps the SDK's `authenticate_request()`:

```python
AuthenticateRequestOptions(
    secret_key=config.CLERK_SECRET_KEY,
    authorized_parties=config.CORS_ORIGINS,
    accepts_token=["session_token"],
)
```

`authorized_parties` reuses `CORS_ORIGINS`, which is already environment-driven
and validated (it refuses `*` while credentials are allowed). This avoids a
second per-environment origin list that could drift out of sync with the first.

The SDK's `authenticate_request` takes an **`httpx.Request`**, not a Starlette
one, so `clerk.py` adapts between them. Only the method, URL, and headers are
read during verification — the body is never inspected — so the adapter builds
a bodyless `httpx.Request` and no request stream is consumed. This matters:
reading the body in a dependency would leave the route handler with an empty
stream.

On failure it raises `HTTPException(401)` with a `WWW-Authenticate: Bearer`
header. It returns the validated claims — never the raw token.

**Email is not a default session-token claim.** Clerk's default token carries
`sub`, `sid`, `iss`, `exp`, `iat`, `nbf`, and `azp` — no email. Two ways to get
one: add a custom JWT template claim, or call the Backend API. This design
takes the second: `fetch_user_email(clerk_user_id, config)` wraps the SDK's
user lookup, and provisioning calls it **lazily, only on the insert path**.

The alternative — a JWT template — would need identical dashboard
configuration across three Clerk applications with no way to detect drift,
which is the same failure mode this design already avoids for CORS origins.
Fetching costs one call per user lifetime and nothing on the hot path, since
returning users short-circuit before the resolver is invoked.

### `auth/dependencies.py`

`get_current_user(request) -> User`:

1. Verify the token via `clerk.py`.
2. JIT-provision (below) using the `sub` claim as `clerk_user_id`, passing a
   lazy email resolver that only runs if a row must be inserted.
3. Return the `User` ORM row.

Routes declare `user: User = Depends(get_current_user)`. Handlers receive a
domain object, not a token or a raw claim dict, so no route needs to know that
Clerk exists.

### User model and provisioning

`models/orm/user.py`:

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `clerk_user_id` | str | Unique, indexed — the `sub` claim |
| `email` | str | Fetched from Clerk's Backend API on insert; nullable, as not every Clerk strategy supplies one |
| `created_at` | datetime | |
| `updated_at` | datetime | |

Registered in `models/orm/__init__.py` — without this the table is invisible
to SQLAlchemy metadata. Accompanied by an Alembic revision; `alembic check`
must report no drift.

`repositories/user_repository.py` gains `get_by_clerk_id`.

**Race safety:** two concurrent first requests from the same new user would
both miss the `SELECT` and both attempt an `INSERT`. Provisioning therefore
does insert → catch `IntegrityError` → rollback → re-fetch, so the loser of
the race returns the winner's row instead of a 500.

### Protected surface

| Endpoint | Auth |
|---|---|
| `GET /health` | Public — Container Apps probes it unauthenticated |
| `GET /integration-messages` | Required |
| `POST /integration-messages` | Required |

### Config

`Config` gains `CLERK_SECRET_KEY`. `pyproject.toml` adds
`clerk-backend-api>=7.0.0,<8` — the SDK's own docs recommend pinning, and the
major is held to avoid an unreviewed breaking change reaching production.

`CLERK_JWKS_URL` becomes dead configuration — the SDK authenticates with the
secret key and manages JWKS fetching and caching internally. It is removed
from `.env.example`, `infra/modules/key-vault/`, `infra/envs/qa/`,
`infra/envs/prod/`, and the DEPLOYMENT.md secrets table. Leaving an unused
secret provisioned is a maintenance hazard, not a harmless leftover.

## Frontend design

### Routes

```ts
index("routes/home.tsx"),                  // public landing
route("sign-in/*", "routes/sign-in.tsx"),
route("sign-up/*", "routes/sign-up.tsx"),
layout("routes/protected.tsx", [           // guard + app shell
  route("integration-test", "routes/integration-test.tsx"),
]),
```

The splat on `sign-in/*` and `sign-up/*` is required — Clerk's components use
sub-paths for multi-step flows (verification, MFA, SSO callback).

### Clerk API surface (verified against `@clerk/react-router` 3.6.14)

This version re-exports `@clerk/react`. Notably **`SignedIn` and `SignedOut`
no longer exist** — they are replaced by `<Show when="signed-in">`. The
existing WIP already uses `Show` correctly.

`<Show>` returns `null` while auth is loading and renders `fallback` only once
loading has settled and the condition is false. The protected layout gets
no-flash behaviour for free — no manual `isLoaded` handling required:

```tsx
<Show when="signed-in" fallback={<RedirectToSignIn />}>
  <AppShell>
    <Outlet />
  </AppShell>
</Show>
```

`when` also accepts `{ role: "admin" }` descriptors, which is the natural seam
for the future KYC-approval admin gate.

### `root.tsx`

Reverts to `<ClerkProvider>` wrapping `<Outlet />` only. The WIP header moves
into the protected layout, so the public landing page stops rendering auth
chrome. The app shell — `UserButton`, theme toggle — belongs to signed-in
pages.

### Styling

Sign-in and sign-up render Clerk's `<SignIn />` and `<SignUp />` with
`appearance` mapped to the existing CSS variables in `app.css`, consistent
with the project UI standard. No hand-rolled Tailwind restyling of Clerk
internals, and no bypassing shadcn variants.

### Token plumbing

`lib/api.ts` keeps its pure, framework-free core. `request()` takes a
`getToken` function and sets `Authorization: Bearer <token>`. The existing
`Content-Type`-only-when-body optimisation stays — the auth header does force
a preflight, but that is unavoidable and the response is cacheable.

New `lib/use-api.ts`:

```tsx
export function useApi() {
  const { getToken } = useAuth()
  return useMemo(
    () => ({
      listIntegrationMessages: () => listIntegrationMessages(getToken),
      sendIntegrationMessage: (body: string) =>
        sendIntegrationMessage(getToken, body),
    }),
    [getToken]
  )
}
```

Memoised on `getToken` so the returned object is referentially stable and safe
to use in a TanStack Query `queryFn` without retriggering fetches.

### Error handling

A 401 surfaces as the existing `ApiError` with `status: 401`. A TanStack Query
`QueryCache`/`MutationCache` `onError` handler catches it globally and calls
Clerk's `redirectToSignIn()`, rather than each route rendering a generic error
card — an expired session is an expected condition, not a failure.

Handling it in the cache rather than per-query means a route added later
inherits the behaviour instead of having to remember it. The handler must
also skip the redirect when already signed out, or a failed call on a public
page would loop.

## Testing

| Area | Test |
|---|---|
| Existing routes | `conftest.py` overrides `app.dependency_overrides[get_current_user]` with a fixture user, so current tests keep passing with a one-line change |
| Verification | Unit tests against a mocked `authenticate_request` — valid, expired, malformed, and missing-header cases |
| Rejection | A request with no token returns 401 and a `WWW-Authenticate` header, with the override removed |
| JIT provisioning | First call inserts; repeat call is idempotent and returns the same row |
| Race | Simulated `IntegrityError` returns the existing row rather than raising |
| Public routes | `/health` still answers without a token |

Tests continue to run against throwaway SQLite via `TestConfig`; no test
requires a live Clerk connection.

## Working-tree drift

The current branch carries changes unrelated to auth that this work will
correct rather than inherit:

- `docker-compose.dev.yml` dropped `depends_on: api` from the frontend
  service. This is an accidental regression and is restored.
- Both compose files and `Dockerfile.dev` now run `npm ci` on every container
  start. That was a workaround for the newly added Clerk dependency; the fix
  is an image rebuild, so the start commands revert to `npm run dev`.

## Documentation

- CLAUDE.md — rewrite the Python-version paragraph for 3.11
- docs/DEPLOYMENT.md — Clerk allowed-origins setup; drop the
  `TF_VAR_clerk_jwks_url` row
- `.env.example` — remove `CLERK_JWKS_URL`

## Risks

| Risk | Mitigation |
|---|---|
| Local Python 3.9.6 cannot install the SDK | Documented in the plan; Docker Compose path already runs 3.11 |
| Clerk allowed origins unset per environment causes opaque failures | Explicit DEPLOYMENT.md step per Clerk application |
| `authorized_parties` tied to `CORS_ORIGINS` couples two concerns | Acceptable — both answer "which browser origins are legitimate", and one list cannot drift from the other |
