# RemitX seeder

A local web app that fills a RemitX environment with realistic, rule-abiding
test data: people who sign up, verify, get paid, deposit and send money over
the last few months, and the staff who review and reconcile after them.

It runs on a developer's machine against **local** (your Docker Compose stack)
or **QA**. It is never deployed: it lives outside `api/` and `frontend/`, no
Terraform or deploy workflow refers to it (a test enforces that), and the UI
binds to `127.0.0.1` only.

Why it exists and why it works the way it does:
[docs/adr/0001-qa-seeder-drives-the-service-layer.md](../../docs/adr/0001-qa-seeder-drives-the-service-layer.md).

## Quick start (local)

Prerequisites: the dev stack running (`docker compose -f docker-compose.dev.yml
up`), which migrates Postgres — creating the platform accounts — and creates
the MinIO bucket.

```bash
cd tools/seeder
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ../../api -e '.[dev]'
python -m remitx_seeder            # opens http://127.0.0.1:8090
```

Pick a target in the header, press **Check the target** on the Status tab, then
**Seed**. The default scenario (90 days, ~80 people) takes under a minute
locally.

The `local` target reads the repo-root `.env`, the same file the API uses.

## Targeting QA

1. Copy `.env.qa.example` to `.env.qa` (gitignored; the pre-commit hook refuses
   any `.env.*` file that is not an `*.example`) and fill it in: the QA Neon
   owner URL, the QA Clerk secret key, the QA bucket keys.
2. Add the QA database host to `"qa" → "database_hosts"` in `targets.json`, in a
   reviewed PR. The seeder refuses every host that is not listed there, and the
   list ships empty.
3. Choose **qa** in the header and check the target.

### Guards

Every command checks these first, and refuses on any failure:

| Guard | Refuses when |
|---|---|
| clerk | the Clerk key is a production key (`sk_live_`). QA's Clerk app is a development instance and production's never is, so this alone keeps a run off prod. |
| database | the database host is not on the target's allowlist in `targets.json` |
| env file | `.env.qa` does not say `SEEDER_TARGET=qa` |
| bucket | the KYC bucket is not the target's bucket in `targets.json` |

A QA run never borrows local settings: connection and credential keys missing
from `.env.qa` are blanked, not filled from the repo-root `.env`.

## The loadtest target

`loadtest` belongs to the load test ([tools/loadtest](../loadtest/README.md))
and seeds the throwaway stack. `make loadtest` runs the seeder inside that
stack with the **seed block from a load-test profile**
(`tools/loadtest/profiles/*.json`), not a scenario under `scenarios/` here.
Stack credentials come from the committed `tools/loadtest/loadtest.env`, which
names only that stack's own database and bucket and no Clerk key, so everyone
it seeds is database-only. It is not meant for the UI.

The default profile's seed is thousands of senders over two weeks, almost all
verified, with beneficiaries and deposits sized well above what they send
(`deposit_headroom`). Rare KYC paths are turned down so a load run is not
spent on abandoned drafts. `clerk_user_cap` is 0. Edit the profile to change
the population or the Locust shape.

## Signing in as a seeded person

Seeded people get `…+clerk_test@example.com` emails. Clerk treats `+clerk_test`
addresses as test addresses: sign in with the email and the code **424242**,
no password. The People tab lists who can sign in.

Clerk development instances hold at most **100 users**, and QA's Clerk app is
one. A scenario's `clerk_user_cap` (default 80) is how many users may exist in
total after a run, counting your testers' own accounts. Staff get Clerk
accounts first, then senders, then recipients; everyone past the cap is
database-only (a `seed_…` Clerk id). Database-only people cannot sign in, but
they fill the admin queues and appear as beneficiaries.

## What a run does

A run replays the last `days` days as a timeline of events. Before each event
the process clock moves to that moment (`time-machine`), so the backend stamps
the replayed time with no change to its code.

| Story | How it happens | Real or simulated |
|---|---|---|
| Staff join and get roles | `UserController.ensure_provisioned`, `UserRoleController.grant` by the IAM admin | real |
| People sign up | Clerk user (with a backdated `created_at`), then `ensure_provisioned`, then a profile mobile through `ProfileController` | real |
| KYC | wizard through `KycOnboardingController` (start, a PATCH per step, submit), documents through `KycDocumentController.store_document` | real |
| Review | analysts claim and request more information, officers approve, reject and override ratings, through `KycController` | real |
| Documents | SPECIMEN ID cards and utility bills drawn with Pillow, some deliberately blurry | generated, uploaded for real |
| Beneficiaries | `BeneficiaryController.create` | real |
| Payout wallets (USD, ZWL, NAD) | verified customers through `AccountController.open_account`; everyone else through `direct.open_payout_account` (they cannot pass KYC) | real, or direct when KYC is impossible |
| Cash-out | external bank account through `BankAccountController`; a payout operator verifies, rejects, or leaves it pending; spare balance leaves through `WithdrawalController.request` | real |
| Cash-in | bank-statement lines, reconciled next working morning by `deposit_service.process_deposits`; mistyped references land pending, and a treasury operator resolves most of them | real |
| Sends | `QuoteController.create_quote`, then `RemittanceController.confirm`, within KYC limits and available balance | real |
| Settlement | the worker's own `settle_remittance` → `burn_treasury_tokens` → `confirm_treasury_burn` | real worker code; the XRPL call is simulated |
| Exchange rates | a replaceable rate provider (`use_rate_provider`) serving a seeded USD/ZAR walk, NAD pegged to ZAR | simulated |
| Treasury | one `treasury_funding` row per run equal to the simulated burns, so the ledger still matches the chain | direct write |

Staff act in office hours (SAST, weekdays); customers act mostly in the
evenings; salaries land on the 25th, at month end or on Fridays, and people
send soon after. Anything scheduled past the end of the window is left
pending, which is how "waiting for a reviewer", "unmatched deposit" and
"quote not yet confirmed" states arise naturally.

**Simulated settlements** use synthetic hashes starting `5EED`; they do not
exist on the XRPL testnet and their explorer links 404. No treasury tokens are
spent.

### The live tail

Set **Live settlements** above 0 to finish a run with a few real transfers: the
seeder signs in as a verified sender (a Clerk session through the Backend API),
calls the target's real API (`POST /quotes`, `POST /remittances`), and waits for
the real worker to settle on the XRPL testnet. It stops before a quote would
take the run past its **budget** in uctusd: the treasury is funded by the
lecturer and RemitX cannot replace what it burns. The target's Redis is only
reachable inside Render, which is why the live tail goes through the API.

## Scenarios

JSON files in `scenarios/`, edited on the Seed tab or by hand. A file only
needs the keys it changes; defaults and descriptions live in
`remitx_seeder/scenario.py`. The same scenario and seed on the same code make
the same people.

With `ensure_every_path` (on by default) the first senders take one each of
the rare paths, so every run has at least one: a PEP (self) and a PEP (family
member), a rejection, a more-information round trip, one left unanswered, an
abandoned draft, a rating override, a tier 2 approval, a high declared volume,
and an application still waiting for a reviewer.

Who the people are comes from `remitx_seeder/data/*.json`: culture-matched
names per nationality, cities and suburbs, occupations with income and payday,
corridors (who sends where, how much, how often) and free-text templates.
Change those to change the population; no code needed.

## Verify, Schema, Runs, Reset

- **Verify** checks the business rules over the whole database, seeded or not:
  balances equal confirmed ledger rows, every remittance is seven legs that
  settle together and match their quote, deposits are consistently owned, KYC
  status matches its history, approvals carry tier, rating and review date,
  every user has correctly named accounts, every beneficiary has a payout
  account. Every seed run ends with it.
- **Schema** reads the live schema: rows per table, which story writes it, and
  columns that are NULL in every row. A table marked *no generator yet* means
  the schema moved on and the seeder has not.
- **Runs** lists the manifest each run writes to `runs/` (gitignored): scenario,
  seed, git commit, counts, refusals and the verify report.
- **Reset** deletes the seeded Clerk users, empties the bucket, drops and
  recreates the schema and runs `alembic upgrade head`, which also creates the
  platform accounts and, when the target has a `PLATFORM_WALLET_ADDRESS`,
  records the treasury's on-chain starting balance. Type `reset <target>` to confirm. Staff roles are not
  restored: grant your testers theirs again on the Access page.

## Keeping it working while the backend changes

The seeder calls the backend's own code, so most rule changes need nothing:
KYC tiers, risk signals and ratings, onboarding steps, jurisdictions and fee
settings are read at run time. When something does break:

1. **CI fails the PR that broke it.** The `seeder` job runs a real seed against
   a throwaway Postgres (fakes for Clerk, storage and the XRPL) and `verify`.
2. A **refusal** in a run (the Runs tab lists them) means a story asked for
   something the rules now forbid: update the story in `remitx_seeder/stories/`.
3. A **new table** shows as *no generator yet* on the Schema tab: add it to
   `COVERAGE` in `schema.py` and a story that fills it through the backend.
4. A write no product flow can make yet goes in `direct.py`, with a docstring
   naming the flow it stands in for. Nothing else writes directly.

## Layout

```
remitx_seeder/
  __main__.py     UI with no arguments; one runner command with them
  runner.py       every database operation, as a child process speaking JSON lines
  guards.py       the checks above
  engine.py       preflight, planning, replay, top-up, verify
  sim.py          the event loop;  clock.py  time travel
  stories/        people.py, kyc.py, money.py, timing.py
  settlement.py   real worker tasks, simulated chain
  generators/     identity numbers, phones, personas, SPECIMEN documents
  data/           the JSON that makes people realistic
  direct.py       the only writes that bypass product flows
  verify.py  schema.py  live_tail.py  reset.py
  ui/             NiceGUI
scenarios/        scenario JSON
targets.json      what each target may touch (reviewed changes only)
tests/            unit tests, and a real seed run against Postgres
```

Every database operation runs in its own process because the target's
settings must be in the environment before `remitx_api` is imported, and a
seed run moves the process clock, which must never touch the UI.

## Tests

```bash
cd tools/seeder
SEEDER_TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/postgres pytest
ruff check . && ruff format --check .
```

`SEEDER_TEST_DATABASE_URL` names a Postgres server the tests can create and
drop databases on; each session migrates its own.

## Known gaps

- `users.last_name` is never set, because no product flow sets it yet (the Schema tab shows it).
- No application reaches `review_due`: reviews fall due 180 to 730 days after
  approval, beyond any window.
- Quotes left to expire keep status `ACTIVE` with a past `expires_at`, as they
  do in the product.
