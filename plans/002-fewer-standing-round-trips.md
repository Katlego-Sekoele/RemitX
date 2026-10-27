# Plan 002: Read KYC standing in four statements, not six

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 94d8a57..HEAD -- api/remitx_api/repositories/kyc_application_repository.py api/tests/test_kyc_controller.py api/tests/test_kyc_risk_assessment.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: none
- **Category**: perf
- **Planned at**: commit `94d8a57`, 2026-10-27

## Why this matters

`KycApplicationRepository.get_standing` runs on `GET /kyc/application`, which
the customer sidebar loads on every app page, and again inside
`DashboardController.get_dashboard`. It currently performs six sequential
statements: latest application, latest stored-verified application, tier
row, risk-rating row, sent totals, stokvel contribution totals. The API is
in `africa-south1` and Neon is not pinned to that region
(`infra/data/modules/neon/main.tf` sets no `region_id`), so each statement
is a cross-region round trip. Six of them, plus the session ping and
`SET LOCAL ROLE`, is a request over a second. Collapsing the two
application queries into one and the two primary-key lookups into one
leaves four statements and drops two round trips from the hottest read
without changing limits.

Stokvel contributions count toward the member's own sending limits. That
is decision D8. `daily_used_zar` and `monthly_used_zar` must stay
`sent + contributed`. Do not drop `contributed_zar`.

`effective_status` is computed in Python (`kyc_lifecycle.effective_status`):
a stored `approved` row whose `next_review_at` is in the past is reported
as `review_due`. Do not reimplement that in SQL.

## Current state

`api/remitx_api/repositories/kyc_application_repository.py` `get_standing`
(lines 156–204) does, in order:

1. `get_latest_for_user` — latest `KycApplication` by `created_at desc`.
2. A second query: latest application whose **stored** `status` is in `VERIFIED_STATUSES` (`approved`, `review_due`). This can be an older row than `latest` when a newer application is in draft or submitted. Tier and rating come from this row, not from `latest`.
3. `db.session.get(KycTier, tier_number)`. `KycTier.tier` is the integer primary key (`api/remitx_api/models/orm/kyc_tier.py`).
4. `db.session.get(KycRiskRatingRecord, rating)` when the verified row has `effective_risk_rating` (override or computed). Primary key is `KycRiskRatingRecord.rating` (`api/remitx_api/models/orm/kyc_risk_rating.py`).
5. `RemittanceRepository().sent_zar(user_id, windows)` — one aggregate, day and month in a single statement (`api/remitx_api/repositories/remittance_repository.py` around line 126).
6. `StokvelContributionRepository().contributed_zar(user_id, windows)` — one aggregate (`api/remitx_api/repositories/stokvel_contribution_repository.py` around line 110).

Reported status uses `latest.effective_status`, not the verified row's status. Missing tier raises `KycRiskRulesMisconfiguredError`. No application → `KycStatus.NOT_STARTED`, tier `KYC_TIER_NONE`, `application_id is None`.

Tests that lock this behaviour:

- `api/tests/test_kyc_controller.py`: `test_standing_for_a_user_with_no_application`, `test_standing_follows_the_latest_application`
- `api/tests/test_kyc_risk_assessment.py`: `test_standing_limits_are_the_tier_scaled_by_risk`

Vocabulary from `CONTEXT.md`: **KYC standing** is the user's verified identity level, tier and risk rating, which sets whether they may send or join a stokvel and their daily and monthly sending limits.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Focused tests | `cd api && .venv/bin/pytest tests/test_kyc_controller.py tests/test_kyc_risk_assessment.py tests/test_kyc_standing.py -q` | exit 0 (`test_kyc_standing.py` may not exist yet; after step 1 it must) |
| Full API tests | `cd api && .venv/bin/pytest -q` | exit 0 |
| Lint | `cd api && .venv/bin/ruff check api/remitx_api/repositories/kyc_application_repository.py && .venv/bin/ruff format --check api/remitx_api/repositories/kyc_application_repository.py` | exit 0 |

If `api/.venv` is missing: `cd api && python3.11 -m venv .venv && .venv/bin/pip install -e '.[dev]'`.

## Scope

**In scope**:
- `api/remitx_api/repositories/kyc_application_repository.py` — `get_standing` only
- `api/tests/test_kyc_controller.py` or a new `api/tests/test_kyc_standing.py` — the regression described below

**Out of scope**:
- `sent_zar` and `contributed_zar` implementations. Call them. Do not inline their SQL.
- `kyc_lifecycle.effective_status` and `VERIFIED_STATUSES`.
- Dashboard SQL, account balances, RLS, frontend, OpenAPI. The response model `KycStanding` / `KycStandingRead` does not change.
- `is_other_user_verified` (it already uses `kyc_latest_status` on Postgres).

## Git workflow

- Branch: `katlego/standing-round-trips-c907` if you are a Cursor cloud agent on this repo; otherwise `advisor/002-standing-round-trips`.
- Commit message style, from `git log`: `Read KYC standing in four statements`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add a regression for "latest status, older verified tier"

`get_standing` is wrong if a newer non-verified application replaces the tier taken from an older approval. Existing tests do not cover that split. Add this test before changing the query, using the helpers those files already use (`make_user`, `insert_application`, `KycController` or `KycApplicationRepository`).

Shape:

- User with an approved application that has a granted tier and a risk rating.
- A newer application for the same user in a non-verified stored status (`submitted` is enough).
- `get_standing` reports the newer application's status, and the approved application's tier (not `KYC_TIER_NONE`).

Run it once against the current code. It must pass before you edit `get_standing`. If it fails on unchanged code, STOP: the assumption about which row supplies the tier is wrong.

**Verify**: `cd api && .venv/bin/pytest tests/test_kyc_standing.py::test_newer_draft_keeps_the_approved_tier -q` → exit 0 (name the test that; put it in `api/tests/test_kyc_standing.py`).

### Step 2: One application query, one tier/rating query

Rewrite only the body of `get_standing`.

**Statement 1.** `SELECT` the caller's `KycApplication` rows `ORDER BY created_at DESC`. A person has a handful of applications; do not add pagination. In Python:

- `latest` = the first row, or `None`.
- `verified` = the first row whose **stored** `status` is in `VERIFIED_STATUSES`. Do not use `effective_status` for this pick. An `approved` row past `next_review_at` is still stored as `approved`, which is in `VERIFIED_STATUSES`.

**Statement 2.** Load the tier and, when `verified` has an `effective_risk_rating`, the rating, in one statement:

```python
select(KycTier, KycRiskRatingRecord)
.select_from(KycTier)
.outerjoin(
    KycRiskRatingRecord,
    KycRiskRatingRecord.rating == rating,  # rating is the Python string or None
)
.where(KycTier.tier == tier_number)
```

When `rating` is `None`, outer-join on a false condition (`KycRiskRatingRecord.rating == None` is wrong under SQL NULL; use `literal(False)` or skip the join and select only `KycTier`). Missing tier still raises `KycRiskRulesMisconfiguredError`. A rating string that matches no row yields `rating_record is None`, same as `session.get` returning `None` today.

**The two aggregates stay as the existing calls** `sent_zar` and `contributed_zar`. Together with the two statements above that is four statements inside `get_standing` (was six). Do not fuse the aggregates into the application query.

Keep the `KycStanding(...)` construction identical, including `daily_used_zar=sent.day_zar + contributed.day_zar`.

**Verify**: `cd api && .venv/bin/pytest tests/test_kyc_controller.py tests/test_kyc_risk_assessment.py tests/test_kyc_standing.py -q` → exit 0.

### Step 3: Lint and the full suite

**Verify**: `cd api && .venv/bin/ruff check --fix api/remitx_api/repositories/kyc_application_repository.py api/tests/test_kyc_standing.py && .venv/bin/ruff format api/remitx_api/repositories/kyc_application_repository.py api/tests/test_kyc_standing.py && .venv/bin/pytest -q` → exit 0.

## Test plan

- New: `test_newer_draft_keeps_the_approved_tier` in `api/tests/test_kyc_standing.py`.
- Do not delete `test_standing_for_a_user_with_no_application`, `test_standing_follows_the_latest_application`, or `test_standing_limits_are_the_tier_scaled_by_risk`.
- Verification: `cd api && .venv/bin/pytest -q` → all pass.

## Done criteria

- [ ] `get_standing` no longer calls `get_latest_for_user` and a second application query
- [ ] `get_standing` no longer calls `db.session.get` twice for tier and rating
- [ ] `sent_zar` and `contributed_zar` are still both added into the used totals
- [ ] `cd api && .venv/bin/pytest -q` exits 0
- [ ] ruff check and format check exit 0 on the touched files
- [ ] No files outside the in-scope list are modified
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- Step 1's new test fails on the unmodified repository.
- `VERIFIED_STATUSES` is not `{approved, review_due}` anymore.
- Preserving behaviour seems to require changing `effective_status`, limit windows, or D8 contribution accounting.
- You are about to emit a different `KycStanding` field or a migration.

## Maintenance notes

- Anyone adding a field to standing that comes from another table must not put a `session.get` back in a loop. Extend statement 2.
- Reviewer: the verified row is chosen by stored status, and the reported status still comes from `latest.effective_status`. Those are different rows on purpose.
- Deferred: fusing `sent_zar` and `contributed_zar` into one statement. Worth it only if this 4-statement read is still over a second after deploy. Do not do it here; the aggregate SQL is easy to get wrong (failed legs, SAST windows, fee-included `amount_zar`).
