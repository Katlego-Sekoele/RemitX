# `remittance-quotes` branch — work summary

## 1. Branch setup & sync

- Found `main` had drifted behind both `origin` and the upstream fork; fast-forwarded local `main` to `upstream/main` (which had merged the `deposits` PR plus some infra/render-migration work) and pushed it to `origin/main`.
- Created `remittance-quotes` off the updated `main`, pushed and tracked to `origin`.

## 2. Bug found and fixed: two divergent Alembic heads

`main` had `f28d4a6e9c13` (deposits chain) and `57b763cacca1` (rbac/user-profile merge) as two unreconciled heads — `alembic upgrade head` failed outright (confirmed locally). Added `V20260912_1743__merge_deposits_and_rbac_heads.py`, an empty merge migration reconciling them into one head — same pattern as the existing merge migration in this repo.

## 3. Beneficiaries (brief requires this; nothing existed yet)

- `models/orm/beneficiary.py` — `Beneficiary` model (`V20260912_1744__create_beneficiaries.py`): `sender_user_id` (the sender), `linked_user_id` (must be an existing registered User — no free-standing contacts), `payout_currency` (one of `PAYOUT_CURRENCIES`, DB CHECK `beneficiaries_payout_currency_valid`), and `relationship` constrained to a fixed set (`RELATIONSHIPS`: `partner`/`parent`/`child`/`sibling`/`relative`/`friend`/`employee`/`other`) via a DB CHECK constraint (`beneficiaries_relationship_valid`).
- `Beneficiary` carries **no** `first_name`/`last_name`/`email`/`mobile_number`/`country` columns at all — those are read fresh from the linked `User` via a join everywhere a beneficiary is displayed (`BeneficiaryRepository`'s list queries, `BeneficiaryController`). `User` now has all of those columns itself (`first_name`, `last_name`, `mobile_number`, `country`, `email`), so nothing needs to live twice.
- Migration, repository, controller, schemas, routes — `POST /beneficiaries/create-beneficiary`, `GET /beneficiaries/get-beneficiary-list`, `GET /beneficiaries/lookup-by-reference` (see §5), all customer-authenticated and scoped to the caller's own contacts.

## 4. Exchange rates

- `models/orm/exchange_rate.py` + `V20260912_1745__create_exchange_rates.py`.
- `services/exchange_rate_provider.py` — `ExchangeRateApiProvider` calls the real exchangerate-api.com pair-conversion endpoint via `httpx`, behind a `RateProvider` protocol so tests can fake it instead of monkeypatching `httpx` directly.
- `services/exchange_rate_service.py` — `get_active_rate(base_currency, quote_currency)`: lazy fetch-on-demand (no cron), reuses a valid stored rate, fetches fresh when expired (`Config.RATE_FIXING_INTERVAL_HOURS` validity), falls back to the most recent stored rate on API failure if it's within `Config.MAX_RATE_STALENESS_HOURS`, otherwise raises `RateUnavailableError` rather than fabricate a rate. Also raises `UnsupportedCurrencyError` up front for any pair outside `SUPPORTED_CURRENCIES` (`USD`, `ZAR`, `ZWL`, `NAD`).
- Fee/limit/timing constants live directly on `Config` (`api/remitx_api/config.py`), not a separate `quote_config.py`: `QUOTE_TTL_MINUTES`, `FIXED_FEE_ZAR`, `PERCENTAGE_FEE_RATE`, `FX_MARGIN_RATE`, `CASH_OUT_FEE_RATE`, `DAILY_LIMIT_ZAR`(`_UNVERIFIED`), `MONTHLY_LIMIT_ZAR`(`_UNVERIFIED`) — all env-overridable, fees explicitly commented as stand-ins.
- Added `EXCHANGE_RATE_API_KEY` to `config.py` and `.env.example`.

## 5. Beneficiary reference-code lookup

`GET /beneficiaries/lookup-by-reference?account_reference=X`: a sender pastes in the beneficiary's **fiat** account reference (e.g. `sian1-zar` — the same one shared off-platform for EFT deposits, resolved the same way as deposit matching via `AccountRepository.get_user_account_by_reference`) and gets back a name preview (`BeneficiaryLookupResponse`) before confirming. Matches on the specific account rather than the bare `base_reference`, which future-proofs the lookup for a hypothetical future where a user holds more than one fiat account. Rejects:
- unknown reference → 404 (`LookupByReferenceError`)
- a reference to the beneficiary's `uctusd` account instead of their fiat one → 400 (`NotAFiatAccountError`)
- looking up your own reference → 400 (`CannotAddSelfError`)

This resolves the gap that previously existed: there was no way for a sender to obtain a `linked_user_id` UUID at all before adding a beneficiary.

## 6. Quotes — the actual feature requested

- `models/orm/quote.py` + `V20260912_1746__create_quotes.py`, matching the doc's `quotes` schema.
- `services/quote_service.py` — one shared pricing helper, `price_remittance`, behind two entry points:
  - `create_quote(sender_user_id, beneficiary_id, sender_amount)` — the real, beneficiary-bound flow. Checks: sender exists, KYC-approval gate (`KycNotApprovedError`), a (documented as simplified) daily-limit ceiling check against `Config.DAILY_LIMIT_ZAR` (`LimitExceededError`), beneficiary-ownership check (`UnknownBeneficiaryError`), available-balance check (`InsufficientBalanceError`) via `AccountRepository.get_available_balance` (nets out the sender's own pending outgoing transactions, not just raw balance — the actual double-spend fix). Produces a priced, time-boxed `Quote` row (`Config.QUOTE_TTL_MINUTES` expiry) — doesn't touch `transactions` or any account balance, since nothing is spent until a remittance is confirmed against the quote.
  - `preview_quote(sender_amount, sender_currency, receiver_payout_currency)` — a stateless "what would X currency become in Y currency" calculation, no beneficiary, nothing persisted, no KYC/balance/limit checks. Lets a sender browse rates before picking a beneficiary.
- `price_remittance` computes: the sender-currency→token rate and amount (`_token_rate`, inverted so callers multiply not divide), the fixed ZAR fee converted into the sender's currency (`_convert_zar_fee_to_sender_currency`, 1:1 when already ZAR), percentage fee + FX margin, and a direct sender-currency→payout-currency conversion (`_direct_fiat_rate`) for a receiver-side cash-out estimate (`receiver_amount`/`receiver_payout_fee`/`receiver_payout_estimate`) — a display estimate only, since no real cash-out flow exists yet.
- Controller (`QuoteController`), schemas (`QuoteCreateRequest`/`QuoteRead`, `QuotePreviewRequest`/`QuotePreviewRead`), routes (`POST /quotes/create-quote`, `POST /quotes/preview-quote`), each service error mapped to the right HTTP status (403 KYC, 400 limit/balance/unsupported-currency/value errors, 503 rate-unavailable).

## 7. Tests

5 test files touching this work, 121 passed / 2 skipped as of the last full run:
- `test_account_repository.py` — includes `test_available_balance_excludes_own_pending_outgoing_legs`, the double-spend fix's test.
- `test_exchange_rate_service.py` (renamed from an earlier `test_rate_service.py`) — stored-rate reuse, expired-rate refetch, provider-failure fallback, provider-failure-with-no-fallback refusal, unsupported-currency rejection.
- `test_beneficiaries_route.py` — auth rejection, invalid sort, the four lookup-by-reference outcomes (success/unknown/token-account/self), create+list happy path, missing-contact-info 422, invalid payout currency/relationship, unknown linked user, list scoping to the caller only.
- `test_quote_service.py` — full field computation, direct-rate-unavailable blocking creation, non-ZAR sender currency fee conversion, the double-spend/available-balance test, unverified-sender rejection, daily-ceiling rejection, not-your-beneficiary rejection, 15-minute expiry.
- `test_quotes_route.py` — auth rejection (create and preview), create end-to-end, insufficient-balance 400, caller-not-in-DB 400, preview end-to-end with no beneficiary needed, preview unsupported-currency 400.
- Plus a `verified_client` fixture in `conftest.py` (a DB-persisted, KYC-approved user — the existing fixtures were never persisted to the DB, which quotes/beneficiaries needed).

## 8. Real bugs found and fixed along the way (not just test artifacts)

- `exchange_rate_service.py`'s staleness fallback broke on SQLite's naive-datetime round-trip — fixed with explicit tz normalization.
- `quote_service.py` wasn't quantizing computed token/fee/rate amounts, relying implicitly on DB column truncation (backend-inconsistent) — now explicit (`.quantize(Decimal("0.00000001"))`) so SQLite and Postgres can't disagree on stored values.
- Beneficiary creation relied entirely on a DB CHECK constraint for "mobile or email required," which surfaced as an unhandled 500 — moved into `BeneficiaryController.create` as `MissingContactInfoError` → clean 422 (see §9 for why it couldn't stay a Pydantic validator or a CHECK constraint).
- The fixed ZAR fee had no currency-generality: it's now converted into `sender_currency` via each currency's USD/token peg at quote time, so a non-ZAR sender still gets a correct fixed-fee component.

## 9. Follow-up fixes and the beneficiary-lookup feature (after the initial build)

- **`Beneficiary.relationship` and `payout_currency` constrained to fixed sets** via DB CHECK constraints (`beneficiaries_relationship_valid`, `beneficiaries_payout_currency_valid`) — matching every other enum-like field in this codebase (account types, payment methods, permissions, KYC statuses).
- **Closed a drift risk**: `payout_currency`/`relationship` are plain `str` on the request schema plus `model_validator`s checking membership against the real constants directly (`PAYOUT_CURRENCIES`, `RELATIONSHIPS`) — not a second, hand-typed `Literal[...]` copy that could silently disagree with the DB if either list ever changed.
- **Field validation** on `BeneficiaryCreateRequest`: `payout_currency`/`relationship` validated against the real tuples, invalid values → 422.
- **`sort` query param on `GET /beneficiaries/get-beneficiary-list` de-hardcoded**: plain `str` validated against `BENEFICIARY_SORT_OPTIONS` via `InvalidSortOptionError` → 422, fixing a real bug where any invalid value previously fell through silently to "newest" instead of erroring.
- **Route paths use explicit verbs** (user's preference over strict REST conventions): `POST /beneficiaries/create-beneficiary`, `GET /beneficiaries/get-beneficiary-list`, `GET /beneficiaries/lookup-by-reference`; quotes follow the same pattern (`POST /quotes/create-quote`, `POST /quotes/preview-quote`).
- **Field rename**: `owner_user_id` → `sender_user_id` throughout (model, migration, repository, controller, route, `quote_service.py`, tests) for clarity.
- **Beneficiary reference-code lookup** — see §5. Matches on the beneficiary's **fiat** account reference (e.g. `sian1-zar`), not the `uctusd` settlement reference — a sender wouldn't normally know or share the latter. Confirmed with the user: a remittance will only ever *settle* to the beneficiary's `uctusd` account (ruled out a bigger settlement redesign); the lookup itself just needs a reference the sender would plausibly have.
- **`Beneficiary` normalized further than originally planned**: `first_name`/`email` were dropped first, on the reasoning that a second copy would go stale the moment the linked user's own details change, with no way to propagate the update. `last_name`/`mobile_number`/`country` were expected to stay on `Beneficiary` short-term (no equivalent `User` columns existed yet) but `User` gained all three, so they were removed from `Beneficiary` too — it now carries only `payout_currency` and `relationship` beyond the two user-id FKs. The "mobile or email required" check accordingly lives in `BeneficiaryController.create` (`MissingContactInfoError`), since it needs the resolved `User` row, not the request body.
- **Documented a forward-looking assumption** in `Transaction_Flow_Context.md`: every user currently defaults to a ZAR account at signup (hardcoded); the intended eventual design is a login/signup step where the user picks their own default currency, with ZAR-by-default only as the fallback until that exists.

## Done since the last pass

- `Transaction_Flow_Context.md` updates (beneficiaries table/ERD, exchange rates writeup, fee stand-in note, config, limit-ceiling caveat) — done, across the beneficiary-lookup commit and the quotes commit.
- Full suite green: 121 passed, 2 skipped.

## Still open

- `ruff check .` currently reports one real lint error: `exchange_rate_provider.py` has a trailing inline comment (`# TODO: Consider if this is neeeded or nto`) pushing a line past 88 cols. Needs a cleanup pass + commit.
- `Transaction_Flow_Context.md`'s own open-questions list still flags: the simplified (non-running-total) daily-limit check, the sender's raw-vs-available-balance double-spend window as a documented limitation beyond the fix already made, and — not something this branch attempted — that no quote-receipt/lookup endpoint exists yet for browsing past quotes from transaction history.
