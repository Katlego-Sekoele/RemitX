# Plan 001: Serve account balances in one SQL statement

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 94d8a57..HEAD -- api/remitx_api/controllers/account_controller.py api/remitx_api/repositories/account_repository.py api/remitx_api/models/orm/transaction.py api/tests/test_account_repository.py api/tests/test_accounts_route.py`
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

The API runs on Cloud Run in `africa-south1`. Postgres is Neon, and
`neon_project` does not set a region (`infra/data/modules/neon/main.tf`),
so it is not in Johannesburg. Each SQL statement is its own network round
trip. `GET /accounts` is on every customer page (sidebar and home) and
currently runs two statements per account after the list query. Two
accounts — the signup default — is five statements. That is enough, with
the connection ping and `SET LOCAL ROLE`, to put this endpoint over a
second. One grouped query removes that multiplier. The response shape
stays the same.

## Current state

- `api/remitx_api/controllers/account_controller.py` — `AccountController.get_accounts` builds one view per account and calls `get_available_balance` inside the loop (about lines 240–260):

```python
accounts = sorted(
    self._accounts.list_user_accounts(user_id), key=_display_order
)
return [
    AccountView(
        ...
        available_balance=_money(
            self._accounts.get_available_balance(account.account_id)
        ),
    )
    for account in accounts
]
```

- `api/remitx_api/repositories/account_repository.py` — `get_available_balance` (about lines 266–284) loads the account again, then sums in-flight outgoing legs. `credit_account_id` is the source of a leg (money leaving the account). Both `pending` and `processing` count. A comment in that method says `GET /accounts` must use this unlocked read, not `get_available_balance_locked`.
- `list_user_accounts` (about lines 159–168) is `SELECT` of `Account` where `user_id` and `type == TYPE_USER`.
- `api/remitx_api/models/orm/transaction.py` — `transactions` has no index on `credit_account_id`. The only extra index is the partial unique index `uq_transactions_one_token_burn_per_quote` on `quote_id`. Copy that `postgresql_where` / `sqlite_where` style if you add an index on the model.
- Available balance is already specified by tests in `api/tests/test_account_repository.py` (`test_available_balance_excludes_own_pending_outgoing_legs`, `test_available_balance_excludes_own_processing_outgoing_legs`) and `api/tests/test_accounts_route.py` (`test_new_user_has_two_accounts_with_zero_available_balance` and the cases that expect `"500.00"` / a negative token balance).
- Row-level security: commit `1ad0606` already copies `app.current_user_id` once per transaction. Do not touch `api/remitx_api/db/rls.py`.
- Conventions: repositories flush via `db.session` and do not commit inside a read. Money is `Decimal`. Match the existing repository docstrings (why the query exists, not a restatement of the SQL).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Tests | `cd api && .venv/bin/pytest tests/test_account_repository.py tests/test_accounts_route.py tests/test_withdrawal_repository.py -q` | exit 0 |
| Full API tests | `cd api && .venv/bin/pytest -q` | exit 0 |
| Lint | `cd api && .venv/bin/ruff check api/remitx_api/repositories/account_repository.py api/remitx_api/controllers/account_controller.py api/remitx_api/models/orm/transaction.py && .venv/bin/ruff format --check api/remitx_api/repositories/account_repository.py api/remitx_api/controllers/account_controller.py api/remitx_api/models/orm/transaction.py` | exit 0 |

If `api/.venv` is missing: `cd api && python3.11 -m venv .venv && .venv/bin/pip install -e '.[dev]'`.

Postgres lane (`TEST_DATABASE_URL=... pytest -m postgres`) is optional. Unit tests use SQLite. Do not skip them because Postgres is unset.

## Scope

**In scope**:
- `api/remitx_api/repositories/account_repository.py`
- `api/remitx_api/controllers/account_controller.py`
- `api/remitx_api/models/orm/transaction.py` (index only)
- `api/alembic/versions/` — one new migration if `alembic revision --autogenerate` emits the index
- `api/tests/test_account_repository.py` — one new test

**Out of scope**:
- `get_available_balance` and `get_available_balance_locked` — spend checks (`withdrawal_service`, `remittance_service.confirm_remittance`) stay row-locked and per account.
- `get_platform_accounts` — different caller, do not "clean it up" in this plan.
- `api/remitx_api/db/rls.py`, quote pricing, KYC standing, frontend.
- Any change to the `AccountRead` JSON fields.

## Git workflow

- Branch: `katlego/account-balance-query-c907` if you are a Cursor cloud agent on this repo; otherwise `advisor/001-account-balance-query`.
- Commit message style, from `git log`: `Serve account balances in one query`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add a grouped read and cover it with the existing balance cases

Add `AccountRepository.available_balances_for_accounts(account_ids: list[uuid.UUID]) -> dict[uuid.UUID, Decimal]`.

One statement:

- `SELECT credit_account_id, COALESCE(SUM(amount), 0)` from `transactions`
- `WHERE credit_account_id IN :ids AND status IN ('pending', 'processing')`
- `GROUP BY credit_account_id`

Accounts with no in-flight legs are absent from the result. Callers treat a missing id as `Decimal("0")`.

Do not call `get_by_id` inside this method. The controller already has the `Account` rows.

Add a test in `api/tests/test_account_repository.py` next to `test_available_balance_excludes_own_pending_outgoing_legs`. Create two user accounts, put a `pending` leg on one and a `processing` leg on the other, call `available_balances_for_accounts` with both ids, and assert each result equals `get_available_balance` for that account. Include a third account id with no legs and assert it is missing from the dict.

**Verify**: `cd api && .venv/bin/pytest tests/test_account_repository.py -q` → exit 0.

### Step 2: Use it from `get_accounts`

In `AccountController.get_accounts`, load the accounts once, call `available_balances_for_accounts` once, and set `available_balance` to `_money(account.account_balance - pending)`.

`get_accounts` must not call `get_available_balance`.

**Verify**: `cd api && .venv/bin/pytest tests/test_accounts_route.py tests/test_account_repository.py -q` → exit 0. `rg "get_available_balance" api/remitx_api/controllers/account_controller.py` shows calls only in `get_account` (the single-account method) and nowhere in `get_accounts`.

### Step 3: Index the in-flight sum

On `Transaction.__table_args__`, add a non-unique index named `ix_transactions_credit_inflight` on `credit_account_id`, with `postgresql_where=text("status IN ('pending', 'processing')")` and the same predicate for `sqlite_where`, matching the burn index already in that file.

Generate the migration from `api/` with the venv's alembic (`alembic revision --autogenerate -m "index in-flight outgoing legs"`). Review the file: it may only contain this index. Delete any unrelated drift the autogenerate picked up. If autogenerate is impossible because no Postgres URL is configured, hand-write a revision whose `upgrade` is `op.create_index("ix_transactions_credit_inflight", "transactions", ["credit_account_id"], postgresql_where=sa.text("status IN ('pending', 'processing')"))` and whose `downgrade` drops that index. Follow `api/alembic/README.md`: do not invent the filename; `file_template` in `api/alembic.ini` sets `V<UTC yyyyMMdd_HHmm>__...`.

**Verify**: `cd api && .venv/bin/ruff check api/remitx_api api/alembic/versions && .venv/bin/pytest -q` → exit 0. `rg "ix_transactions_credit_inflight" api` shows the model and the migration.

## Test plan

- New test: `test_available_balances_for_accounts_matches_per_account_read` in `api/tests/test_account_repository.py`, as specified in step 1. Pattern: the two existing available-balance tests in that file.
- Existing route tests stay the contract for the JSON (`available_balance` strings). Do not weaken them.
- Verification: `cd api && .venv/bin/pytest -q` → all pass.

## Done criteria

- [ ] `GET /accounts` path in `get_accounts` issues one account list and one aggregate, not one aggregate per account
- [ ] `get_available_balance` / `get_available_balance_locked` still exist and are unchanged in behaviour
- [ ] `cd api && .venv/bin/pytest -q` exits 0
- [ ] `cd api && .venv/bin/ruff check api/remitx_api api/alembic && .venv/bin/ruff format --check api/remitx_api api/alembic` exits 0
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The `get_accounts` loop no longer calls `get_available_balance` (someone already fixed this).
- Matching `get_available_balance` would require changing which statuses count. Both `pending` and `processing` must still be subtracted. Confirmed legs must not be subtracted. The ledger balance column is the confirmed balance.
- Autogenerate emits changes to tables other than an index on `transactions`. Do not apply those; report them.
- The fix appears to require changing `AccountRead` or the OpenAPI spec.

## Maintenance notes

- A new in-flight status on `transactions` must be added to both `get_available_balance` and `available_balances_for_accounts`, and to the partial index predicate, or the list and the spend check will disagree.
- `get_available_balance_locked` stays the spend path. Do not route confirms through the grouped read.
- Reviewer: confirm a user with a `processing` burn leg still sees that amount held on `GET /accounts` (covered by the repository test if step 1 included a `processing` leg).
