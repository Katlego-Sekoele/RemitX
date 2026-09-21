# `remittance-settlement` — everything changed vs `main`

Generated 2026-09-21. Scope: `git diff main...HEAD` (merge-base `3e152af`) plus the currently uncommitted working-tree changes on top of the latest commit (`ef527d6 settlement draft`). 60 tracked files touched, 4 new untracked files, ~6,200 insertions.

This branch was reset to start from `remittance-quotes`'s tip (beneficiaries + exchange rates + quotes already in place) and adds remittance confirmation, async settlement, and a real XRPL testnet burn. Two existing docs go deeper on the "why" behind specific decisions: [REMITTANCE_QUOTES_BRANCH_SUMMARY.md](REMITTANCE_QUOTES_BRANCH_SUMMARY.md) and [REMITTANCE_SETTLEMENT_BRANCH_SUMMARY.md](REMITTANCE_SETTLEMENT_BRANCH_SUMMARY.md).

## 1. Beneficiaries

Brief-required feature; nothing existed on `main` before this branch.

- **New:** `models/orm/beneficiary.py`, `V20260912_1744__create_beneficiaries.py`, `repositories/beneficiary_repository.py`, `controllers/beneficiary_controller.py`, `models/schemas/beneficiary.py`, `routes/beneficiaries.py`, `tests/test_beneficiaries_route.py`.
- `Beneficiary` stores only `sender_user_id`, `linked_user_id` (must be an existing `User`), `payout_currency`, `relationship` — both constrained to fixed sets via DB `CHECK` constraints. No duplicated name/contact columns; those are read live off the linked `User` via join.
- Reference-code lookup (`GET /beneficiaries/lookup-by-reference`) lets a sender resolve a beneficiary's fiat account reference (e.g. `sian1-zar`) to a name preview before adding them — rejects unknown references, a `uctusd`-account reference, and self-lookup.
- Routes use explicit-verb paths (`POST /beneficiaries/create-beneficiary`, `GET /beneficiaries/get-beneficiary-list`) per the user's stated preference over strict REST nouns.

## 2. Exchange rates

- **New:** `models/orm/exchange_rate.py`, `V20260912_1745__create_exchange_rates.py`, `services/exchange_rate_provider.py` (`ExchangeRateApiProvider`, calls exchangerate-api.com behind a `RateProvider` protocol), `services/exchange_rate_service.py`, `tests/test_exchange_rate_service.py`.
- `get_active_rate`: lazy fetch-on-demand (no cron), reuses a stored rate while valid, refetches when expired, falls back to the most recent stored rate on API failure within a staleness window, otherwise raises rather than fabricating a rate.
- Fee/limit constants added to `config.py`: `QUOTE_TTL_MINUTES`, `FIXED_FEE_ZAR`, `PERCENTAGE_FEE_RATE`, `FX_MARGIN_RATE`, `CASH_OUT_FEE_RATE`, daily/monthly ZAR limits (verified/unverified) — all env-overridable stand-ins. `EXCHANGE_RATE_API_KEY` added to `config.py` and `.env.example`.

## 3. Quotes

- **New:** `models/orm/quote.py`, `V20260912_1746__create_quotes.py`, `services/quote_service.py`, `controllers/quote_controller.py`, `models/schemas/quote.py`, `routes/quotes.py`, `tests/test_quote_service.py`, `tests/test_quotes_route.py`.
- `create_quote` (beneficiary-bound, persisted): KYC-approval gate, simplified daily-limit ceiling check, beneficiary-ownership check, available-balance check (nets out the sender's own pending outgoing legs — the double-spend fix), produces a time-boxed `Quote` (`QUOTE_TTL_MINUTES` expiry).
- `preview_quote` (stateless): rate/fee preview with no beneficiary, no persistence, no balance/KYC checks.
- Shared pricing helper `price_remittance` computes token rate, fixed-fee currency conversion, percentage fee + FX margin, and a receiver-side cash-out estimate.
- **Redesigned (uncommitted, `V20260921_0900__quotes_reference_users.py`):** `Quote.sender_account_id`/`beneficiary_account_id` replaced with `sender_user_id`/`beneficiary_user_id` — a quote is "from this sender, to this beneficiary," not a frozen ledger row; the actual `Account` is resolved on demand via `AccountRepository.get_user_account`.

## 4. Remittance confirmation (Phase B2)

- **New:** `models/orm/remittance.py`, `V20260920_1210__create_remittances.py`, `repositories/remittance_repository.py`, `services/remittance_service.py`, `controllers/remittance_controller.py`, `models/schemas/remittance.py`, `routes/remittances.py` (`POST /remittances`), `tests/test_remittance_service.py`, `tests/test_remittances_route.py`.
- `confirm_remittance(sender_user_id, quote_id)`: validates quote ownership, flips `Quote` ACTIVE→USED *before* the balance re-check (ordering fix — checking balance first would misreport insufficient balance on a repeat-confirm), then inserts pending ledger legs sharing one `quote_id` and enqueues settlement after commit.
- **Leg count evolved during the branch: 4 → 6 → 7.** Latest (uncommitted) shape: fee+margin → fee revenue; net → bank account; treasury → sender token account; sender token account → beneficiary token account; beneficiary token account → treasury (pass-through unwind); **treasury → UCTUSD issuer (`burn`, new)**; platform fiat account (beneficiary's country) → beneficiary's own fiat account (`payout`, renamed from `remittance`). The beneficiary never holds a resting `uctusd` balance — a deliberate deviation from the brief's literal wording, confirmed with the user.
- `AccountRepository.get_or_create_user_account` added to lazily provision a beneficiary's fiat account the first time they receive money in that currency.

## 5. Settlement worker — now a real XRPL testnet burn (uncommitted, biggest change since the last commit)

`api/remitx_worker/tasks.py` and `api/remitx_api/services/queue_service.py` were restructured from a single guarded-update `settle_remittance` task into a three-task pipeline, and a real on-chain call was added:

- **New:** `api/remitx_worker/xrpl_service.py` — `burn_tokens(amount)` submits a `Payment` of `uctusd` from the treasury wallet back to its issuer on the XRPL testnet (issued-currency burn = return-to-issuer), using `Fernet`-decrypted treasury seed + `XRPL_ENCRYPTION_KEY`. Mirrors `platform_wallet/scripts/create_xprl_platform_wallet.py`'s submit/check/return-hash shape (duplicated on purpose to keep the standalone setup script and app packages uncoupled).
- `settle_remittance(quote_id)` — now just checks a pending `burn` leg exists and hands off to `burn_treasury_tokens`; no longer itself confirms/credits anything.
- `burn_treasury_tokens(quote_id)` (new task) — claims the `burn` leg via a guarded transition to a new `processing` status (not straight to `confirmed`, since a real network call sits in between), submits the XRPL `Payment`, and enqueues `confirm_treasury_burn` with the result (or `None` on failure).
- `confirm_treasury_burn(quote_id, tx_hash)` (new task) — the only step that actually confirms and credits. On success, flips every `pending`/`processing` leg in the group to `confirmed`, stores `tx_hash` on the burn leg, and credits destination account balances, all in one commit. On failure (`tx_hash is None`), flips the whole group to `failed` — a pure status change, since nothing was ever credited.
- `models/orm/transaction.py` — new `TYPE_BURN`, `TYPE_PAYOUT` transaction types, new `STATUS_PROCESSING` status, new `xrpl_tx_hash` column (unique, nullable).
- `config.py` — new `XRPL_TESTNET_URL`, `UCTUSD_ISSUER`, `UCTUSD_CURRENCY_CODE_HEX` (shared defaults with the platform-wallet setup script).
- `queue_service.py` — new `enqueue_burn_treasury_tokens` / `enqueue_confirm_treasury_burn`, both wake the Render worker same as the existing enqueue helpers.
- **New migration:** `V20260921_1400__add_burn_and_payout_transaction_types.py` — additive `CHECK`-constraint widening for the new type/status values plus `xrpl_tx_hash`.
- **New test:** `tests/test_worker_burn_treasury_tokens.py`.
- `tests/test_worker_settle_remittance.py` rewritten for the new three-task split.

## 6. Currency account endpoints (Phase D)

- **New:** `controllers/account_controller.py`, `models/schemas/account.py`, `routes/accounts.py` (`GET /accounts`, `GET /accounts-history?account_id=...`), `tests/test_accounts_route.py`, `tests/test_account_repository.py`.
- Returns every currency account the caller holds (ZAR + `uctusd`), each with an *available* balance (nets out the account's own pending outgoing legs — same check quotes/remittances use). History endpoint returns one account's ledger legs after an ownership check.

## 7. Migration housekeeping

- `V20260912_1743__merge_deposits_and_rbac_heads.py` — reconciles two divergent Alembic heads that existed on `main` (`f28d4a6e9c13` deposits chain, `57b763cacca1` rbac/user-profile merge).
- `V20260913_1830__add_users_mobile_number.py` — emptied to `pass`; its column-add was redundant with a parallel chain that also added `users.mobile_number`.
- `V20260920_1200__merge_users_profile_branches.py` — merges the resulting two `users`-profile heads.
- `V20260921_0900__quotes_reference_users.py`, `V20260921_1400__add_burn_and_payout_transaction_types.py` — see §3 and §5.

## 8. Other model / repository / schema changes

- `models/orm/account.py`, `models/orm/user.py` — minor field additions supporting the above (user profile fields, account helpers).
- `repositories/account_repository.py` — `list_user_accounts`, `get_or_create_user_account`.
- `repositories/quote_repository.py` — `get_for_sender`, `mark_used` (guarded, `synchronize_session=False`).
- `repositories/transaction_repository.py` — `list_for_account`.
- `repositories/user_repository.py` — minor additions supporting remittance confirmation (`require_by_id`).
- `openapi.py`, `routes/__init__.py` — new `Tag.REMITTANCES`/`Tag.ACCOUNTS`, router registration.
- `scripts/seed_platform_accounts.py` — minor adjustment for new platform accounts (treasury / UCTUSD issuer / per-country fiat).

## 9. Docs

- `api/Transaction_Flow_Context.md` — substantially updated: beneficiaries table/ERD, exchange-rate write-up, fee stand-in notes, the settlement redesign (auto-convert to beneficiary fiat, no resting `uctusd` balance), and the burn/payout leg split.
- `REMITTANCE_QUOTES_BRANCH_SUMMARY.md`, `REMITTANCE_SETTLEMENT_BRANCH_SUMMARY.md` — running work logs for the two feature passes this branch bundles.
- `.env.example` — new XRPL/exchange-rate/fee env vars documented.

## 10. Frontend

- `frontend/openapi.json` regenerated (`python scripts/export_openapi.py`) to pick up `POST /quotes/*`, `POST /beneficiaries/*`, `POST /remittances`, `GET /accounts`, `GET /accounts-history`, and the `QuoteRead` sender/beneficiary field rename. No hand-written frontend UI for any of this yet — noted below as a known gap.
- No other `frontend/` files differ from `main`: the UI work referenced in this branch's commit history (profile page, KYC journey, admin queue, date input, attention badge) already reached `main` independently and was pulled back in via `970d5c9 Merge branch 'main' into remittance-quotes`, so it shows no net diff here.

## Known gaps / explicitly out of scope

- No frontend pages yet for confirming a remittance or viewing account balances/history.
- The cash-out fee (`Config.CASH_OUT_FEE_RATE`) is defined but never actually charged.
- No automatic retry/reclaim for a `transactions` group stuck in `processing`/`failed` (only `IntegrationMessage` has a reclaim path, via `remitx_worker/reclaim.py`).
- Porting the Alembic head-merge fix back to `remittance-quotes`/`main` hasn't been done.
