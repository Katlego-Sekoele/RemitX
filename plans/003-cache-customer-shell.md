# Plan 003: Stop the customer shell from serialising and refetching

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 94d8a57..HEAD -- frontend/app/lib/query-client.ts frontend/app/routes/app/layout.tsx frontend/app/routes/app/index.tsx frontend/app/routes/app/send.tsx frontend/app/components/admin/admin-layout-inner.tsx`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: perf
- **Planned at**: commit `94d8a57`, 2026-10-27

## Why this matters

Even after the API does less SQL, the browser still waits in a chain. The
customer layout renders a full-page loader until `GET /me/permissions`
returns, and only then mounts the page. The home page then waits for
`GET /kyc/application` before it mounts recent transfers, so
`GET /remittances` cannot start. React Query's default `staleTime` is 0
and `refetchOnMount` is true, so every page that calls `getApplication` or
`getAccounts` refetches them on mount. Those two endpoints are the slow
ones (plans 001 and 002). A 30 second fresh window, plus starting the
independent reads together, cuts how often a click pays that cost.
Mutations already call `invalidateQueries` for accounts and the KYC
application (send review, withdrawals, onboarding), and invalidation
refetches active queries regardless of `staleTime`.

## Current state

- `frontend/app/lib/query-client.ts` lines 29–44 set `retry` and `refetchOnWindowFocus: false`. No `staleTime`.
- `frontend/app/hooks/use-permissions.ts` already sets `staleTime: 60_000` on `listMyPermissions`. Leave that hook alone.
- `frontend/app/routes/app/layout.tsx` returns `<PageLoader />` while `useMePermissions().isLoading`, and `<Navigate to="/admin" />` when `access.data?.is_admin`.
- `frontend/app/components/admin/admin-layout-inner.tsx` does the same permissions gate for staff. Do not copy the customer change there: an admin page must not render before the permission list exists.
- `frontend/app/routes/app/index.tsx` lines 41–70: `useQuery(api.kyc.onboarding.getApplication())`, then `{onboarding.data ? ( ... <RecentTransfers limit={RECENT_LIMIT} /> ) : null}`. `RECENT_LIMIT` is 5.
- `frontend/app/routes/app/send.tsx`: `SendFlow` mounts only after onboarding succeeds and `verified` is true (lines 87–102). `listMyBeneficiaries` and `getAccounts` live inside `SendFlow` (lines 175–176), so a verified sender waits out `GET /kyc/application` before those two start.
- UI rules: pages are composed from shadcn in `frontend/app/components/ui/`. Prettier: no semicolons, double quotes, 2-space indent, 80 columns. `npm run lint` is typecheck plus prettier check plus vitest. There is no React component test harness; unit tests are `frontend/app/lib/*.test.ts` and a few route-module tests. Do not add a component test framework.
- `PageLoader` stays the fallback for the marketing/Clerk shell (`frontend/app/components/app-shell.tsx`). Do not change that file. Clerk is intentionally lazy on `/`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Lint and tests | `cd frontend && npm run lint` | exit 0 |
| Unit tests only | `cd frontend && npm test` | exit 0 |

If `node_modules` is missing: `cd frontend && npm ci`.

## Scope

**In scope**:
- `frontend/app/lib/query-client.ts`
- `frontend/app/routes/app/layout.tsx`
- `frontend/app/routes/app/index.tsx`
- `frontend/app/routes/app/send.tsx`

**Out of scope**:
- `frontend/app/components/admin/admin-layout-inner.tsx` and every file under `frontend/app/routes/admin/`.
- `frontend/app/hooks/use-permissions.ts` (already cached for 60s).
- `frontend/app/components/app-shell.tsx`, bundle splitting, Phosphor namespace imports, Recharts.
- `frontend/app/routes/app/stokvel-new.tsx` — same pattern as send, left alone so this change stays reviewable. Do not "fix it while you're here."
- API code and `frontend/openapi.json`.

## Git workflow

- Branch: `katlego/customer-shell-cache-c907` if you are a Cursor cloud agent on this repo; otherwise `advisor/003-customer-shell-cache`.
- Commit message style, from `git log`: `Stop the customer shell refetching on every page`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Default query freshness of 30 seconds

In `query-client.ts`, inside `defaultOptions.queries`, add `staleTime: 30_000` next to `refetchOnWindowFocus: false`. Keep the existing `retry` function exactly.

Do not set `staleTime: Infinity`. Quotes, token rates, and in-flight polling already pass their own `staleTime` or `refetchInterval`; a per-query option overrides this default. `refetchInterval` still polls.

**Verify**: `cd frontend && npx prettier --check app/lib/query-client.ts` → exit 0. `rg "staleTime: 30_000" app/lib/query-client.ts` prints the new line.

### Step 2: Mount the customer outlet while permissions load

In `frontend/app/routes/app/layout.tsx`:

- Keep `useMePermissions()`.
- If `access.data?.is_admin`, still `return <Navigate to="/admin" replace />`.
- Delete the `if (access.isLoading) return <PageLoader />` branch so `<Outlet />` mounts on the first render.
- Remove the `PageLoader` import if nothing else in the file uses it.

An admin whose cache is empty can see one frame of the customer shell, then redirect. That is accepted. Customer data routes are still authenticated and filtered by row-level security. Do not add a second permissions fetch.

**Verify**: `rg "PageLoader" app/routes/app/layout.tsx` prints nothing. `rg "is_admin" app/routes/app/layout.tsx` still shows the navigate.

### Step 3: Start recent transfers with the home page

In `frontend/app/routes/app/index.tsx`, render `<RecentTransfers limit={RECENT_LIMIT} />` even when `onboarding.data` is still undefined. Keep the welcome block and the KYC-dependent copy gated on `onboarding.data` / `verified` as they are today. The card titled "Recent transfers" can show while standing is in flight; `RecentTransfers` already has its own loading state. If it does not, leave its loading behaviour as-is (do not invent a new skeleton library).

**Verify**: `rg "onboarding.data" app/routes/app/index.tsx` no longer wraps `RecentTransfers`.

### Step 4: Start send lookups with the page, not after verification

In `SendPage` (`frontend/app/routes/app/send.tsx`), call:

```ts
useQuery({
  ...api.beneficiaries.listMyBeneficiaries(),
  enabled: onboarding.isPending || verified,
})
useQuery({
  ...api.accounts.getAccounts(),
  enabled: onboarding.isPending || verified,
})
```

Place them beside the existing onboarding query so they subscribe on the first render. While onboarding is pending, `verified` is false and `isPending` is true, so both requests start in parallel with `GET /kyc/application`. When the caller is not verified, `enabled` becomes false and no further refetch is scheduled.

Leave the `useQuery` calls inside `SendFlow`. After step 1 they hit the 30s cache instead of issuing a second network call. Do not thread the results down as props.

Unverified users may issue one beneficiaries request and one accounts request that the UI then ignores. That is the trade for not waiting.

**Verify**: `cd frontend && npm run lint` → exit 0.

## Test plan

No new test file. This repo's frontend tests do not render routes. The lint script runs vitest.

- Verification: `cd frontend && npm run lint` → exit 0, including existing `app/lib` and `app/routes` tests.

## Done criteria

- [ ] `frontend/app/lib/query-client.ts` sets `staleTime: 30_000` on queries
- [ ] `frontend/app/routes/app/layout.tsx` does not return `PageLoader` and still redirects `is_admin` to `/admin`
- [ ] Home renders `RecentTransfers` without waiting for `onboarding.data`
- [ ] `SendPage` subscribes to beneficiaries and accounts while onboarding is pending
- [ ] `cd frontend && npm run lint` exits 0
- [ ] No files outside the in-scope list are modified
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `query-client.ts` already sets a `staleTime`.
- `SendFlow` no longer owns those two `useQuery` calls (the prefetch would not match).
- Admin layout was imported by the customer layout and your edit would remove the staff gate.
- `npm run lint` fails on a file you did not mean to touch. Revert the accidental edit; do not drive-by format the repo.

## Maintenance notes

- A new customer query that must be live on every mount (a quote preview, a payment in flight) has to pass its own shorter `staleTime` or `refetchInterval`. The 30s default will otherwise hide updates until invalidation or remount-after-stale.
- After a mutation, keep using `invalidateQueries` with the generated `queryKey`. Do not `removeQueries`.
- Reviewer: confirm an admin opening `/app` still ends on `/admin`, and that `refetchOnWindowFocus` is still false.
