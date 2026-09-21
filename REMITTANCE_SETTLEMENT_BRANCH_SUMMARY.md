# `remittance-settlement` branch — work summary

Branch was reset to start from `remittance-quotes`'s tip (which already has beneficiaries, exchange rates, and quotes), then built out remittance confirmation (Phase B2), the settlement worker task (Phase C), and currency-account read endpoints (Phase D) per `api/Transaction_Flow_Context.md` §2.

## 1. Branch setup

- `remittance-settlement` was previously identical to `main` (no unique commits). Reset with `git reset --hard remittance-quotes` so it now branches off `remittance-quotes` (commit `970d5c9`), which has beneficiaries + exchange rates + quotes already merged.

## 2. Pre-existing migration conflict, fixed

`remittance-quotes` had two unmerged Alembic heads (`393879e988d7` and `63c9656baaa8`) — both independently added a `users.mobile_number` column, a leftover from `main` being merged into `remittance-quotes` without reconciling the migration chain. A bare merge migration would have replayed both `add_column` calls and failed on Postgres.

- **`api/alembic/versions/V20260913_1830__add_users_mobile_number.py`** — emptied `upgrade()`/`downgrade()` to `pass`; its column-add was redundant with the other chain's.
- **`api/alembic/versions/V20260920_1200__merge_users_profile_branches.py`** (new) — merge migration, `down_revision = ("393879e988d7", "63c9656baaa8")`.
- Result: `alembic heads` now shows one head. (This only fixes it on `remittance-settlement`; the same fix would need porting to `remittance-quotes`/`main` separately.)

## 3. Remittance confirmation (Phase B2)

**New files:**
- `api/remitx_api/models/orm/remittance.py` — `Remittance` ORM. Deliberately lean: `remittance_id`, `quote_id` (FK `quotes.quote_id`, UNIQUE), `tx_id` (FK `transactions.tx_id` — the sender→beneficiary settlement leg), `confirmed_by` (FK `users.id`), `created_at`. Doesn't duplicate any priced field `Quote` already freezes.
- `api/alembic/versions/V20260920_1210__create_remittances.py` — creates `remittances`; also adds the FK `transactions.quote_id → quotes.quote_id` (that column had no FK before since `quotes` didn't exist yet when `transactions` was created).
- `api/remitx_api/repositories/remittance_repository.py` — `RemittanceRepository` + `get_by_quote_id(quote_id)`.
- `api/remitx_api/services/remittance_service.py` — `confirm_remittance(sender_user_id, quote_id)`:
  1. `QuoteRepository.get_for_sender(quote_id, sender_user_id)` — 404-equivalent `QuoteNotFoundError` if not found/not yours.
  2. Guarded `QuoteRepository.mark_used(quote_id, now)` (ACTIVE→USED, `expires_at > now` in the same WHERE) **before** the balance check — ordering matters: checking balance first would misreport "insufficient balance" on a repeat-confirm attempt, since the first confirmation's own legs already count against that balance.
  3. Re-check `AccountRepository.get_available_balance` against `quote.sender_amount` → `InsufficientBalanceError`, rolling back the flip above if it fails (closes Open Question #5 — nothing re-checked balance at confirm time before this).
  4. Inserts 4 `pending` `Transaction` legs sharing `quote_id`: fee+margin combined → Fee Revenue; net → Bank Account; Treasury→sender's own token account; sender's token account→beneficiary (this last one is `Remittance.tx_id`).
  5. Inserts the `Remittance` row, commits once, then `queue_service.enqueue_settle_remittance(quote_id)` — only after commit.
  - Exceptions: `QuoteNotFoundError`, `QuoteNotActiveError`, `InsufficientBalanceError`.
  - Platform account labels hardcoded (`REMITX_SA_FEE_REVENUE_LABEL`, `REMITX_TREASURY_WALLET_LABEL`; reuses `deposit_service.REMITX_SA_BANK_ACCOUNT_LABEL`), matching the existing ZAR-only convention.
- `api/remitx_api/controllers/remittance_controller.py` — `RemittanceController.confirm(...)`, builds a `RemittanceView` receipt by joining the new `Remittance` row with its `Quote`.
- `api/remitx_api/models/schemas/remittance.py` — `RemittanceConfirmRequest`, `RemittanceRead` (uses the canonical `Schema`/`UtcDateTime` from `schemas/base.py`).
- `api/remitx_api/routes/remittances.py` — `POST /remittances` (`{quote_id}` body). 400 for not-found/insufficient-balance, 409 for not-active (already used/expired).

**Modified files:**
- `api/remitx_api/repositories/quote_repository.py` — added `get_for_sender(quote_id, sender_user_id)` and `mark_used(quote_id, now)` (`synchronize_session=False` needed — SQLite round-trips `expires_at` naive while `now` is tz-aware, which breaks SQLAlchemy's default "evaluate" sync strategy on that WHERE).
- `api/remitx_api/repositories/account_repository.py` — added `list_user_accounts(user_id)`.
- `api/remitx_api/repositories/transaction_repository.py` — added `list_for_account(account_id)` (union of `credit_account_id`/`debit_account_id`, newest first).
- `api/remitx_api/models/orm/transaction.py` — `quote_id` now has a real FK to `quotes.quote_id` (dropped the stale "no FK yet" comment).
- `api/remitx_api/services/queue_service.py` — added `SETTLE_REMITTANCE` constant + `enqueue_settle_remittance(quote_id: str)`.
- `api/remitx_api/models/orm/__init__.py` — registered `Remittance`.
- `api/remitx_api/openapi.py` — added `Tag.REMITTANCES`, `Tag.ACCOUNTS` + `TAGS` entries.
- `api/remitx_api/routes/__init__.py` — registered `remittances_router`.

## 4. Settlement worker task (Phase C)

- `api/remitx_worker/tasks.py` — added `settle_remittance(quote_id: str) -> str`:
  - Guarded bulk `UPDATE transactions SET status='confirmed' WHERE quote_id=? AND status='pending'` (same pattern as the existing `process_integration_message`, widened from one `tx_id` to a `quote_id` group).
  - `rowcount == 0` → `"skipped"` (idempotent — a redelivered message matches nothing once the first delivery committed).
  - Otherwise, `SELECT`s the now-confirmed legs' `(debit_account_id, amount)` and applies `increase_balance`-equivalent atomic `UPDATE`s to each destination account, all in one `session_scope()`.
  - Takes `quote_id`, not `remittance_id` — it's the only thing settlement actually needs, and `Quote.quote_id` is UNIQUE on `Remittance` so nothing is lost.

## 5. Currency account endpoints (Phase D)

Originally built as a single `GET /wallet` endpoint, then reworked: there's no separate "wallet" concept anywhere in the data model — it's just the existing `accounts` + `transactions` ledger — so this was renamed to match that (`Account`/`accounts` throughout, no `wallet_controller.py`/`schemas/wallet.py`/`routes/wallet.py`), and split into two endpoints instead of one nested shape. No existing `account_controller.py`/`routes/accounts.py` existed to fold into (only `account_repository.py` + `models/orm/account.py` did), so these are new files following that naming.

Returns **every currency account the caller holds** (ZAR + uctusd today), not just uctusd — per explicit correction mid-build.

- `api/remitx_api/controllers/account_controller.py` — `AccountController`:
  - `get_accounts(user_id) -> list[AccountView]` — one `AccountView` per account from `AccountRepository.list_user_accounts`, each carrying `AccountRepository.get_available_balance` (not the raw stored balance — nets out the account's own still-pending outgoing legs, same balance quotes/remittances check against).
  - `get_account_history(user_id, account_id) -> list[AccountTransactionView]` — a given account's legs via `TransactionRepository.list_for_account`, after an ownership check (`UnknownAccountError` if the account doesn't exist or isn't the caller's — collapses both into one refusal, same pattern as `quote_service.UnknownBeneficiaryError`). Direction per leg: `"in"` when the account is `debit_account_id`, `"out"` when `credit_account_id`.
- `api/remitx_api/models/schemas/account.py` — `AccountRead` (`account_id`, `currency`, `available_balance`), `AccountTransactionRead`.
- `api/remitx_api/routes/accounts.py` — `GET /accounts` (list, with available balance) and `GET /accounts-history?account_id=...` (one account's history; 400 if unknown/not-yours).
- No XRPL tx-hash field (out of scope — only the future withdrawal burn touches the chain). No pagination (matches the existing "return everything" precedent).

## 6. Tests (all passing)

- `api/tests/test_remittance_service.py` (9 tests) — 4-leg amounts/accounts/types correct; quote flips to USED; unknown/foreign/already-used/expired quote rejected; **the Q5 regression test**: two ACTIVE quotes against one balance, confirming the first makes the second fail with `InsufficientBalanceError`; enqueue fires with the right `quote_id` after commit.
- `api/tests/test_remittances_route.py` (4 tests) — 401 anonymous, happy path, 400 unknown quote, 409 confirming twice.
- `api/tests/test_worker_settle_remittance.py` (7 tests, new — first test file to exercise `tasks.py`'s DB logic directly) — all four legs confirm and credit the right accounts; **idempotency**: settling twice doesn't double-credit (the project brief's graded requirement); unknown/malformed `quote_id` → `"skipped"`.
- `api/tests/test_accounts_route.py` (6 tests) — 401 anonymous on both endpoints; new user gets two accounts (ZAR + uctusd) with zero available balance; history for an unknown or someone-else's account is a 400; a confirmed remittance shows correctly on both the sender's and beneficiary's sides, including both directions of the sender's own token pass-through and the available-balance drop from pending legs.

## 7. Regenerated

- `frontend/openapi.json` via `python scripts/export_openapi.py` — picks up `POST /remittances`, `GET /accounts`, `GET /accounts-history`.

## Full test suite status

561 passed, 2 skipped, 1 pre-existing-fixed (`test_openapi.py`'s staleness check, resolved by the regeneration above) as of the last full run.

## Known follow-ups not done here

- Frontend pages for confirming a remittance and viewing account balances/history.
- Withdrawals/cash-out (Phase E) — the only phase that actually touches XRPL (the withdrawal burn), plus the real signing/submission wiring.
- Porting the migration-conflict fix (section 2) back to `remittance-quotes`/`main`.
