<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/remitx-logo-dark.svg">
    <img src="docs/assets/remitx-logo-light.svg" alt="RemitX" width="160">
  </picture>
</p>

<h1 align="center">RemitX</h1>

<p align="center">
  A prototype cross-border FX remittance platform: senders in South Africa pay
  in rand, and settlement runs on the XRPL EVM <strong>Testnet</strong>.
</p>

---

RemitX is the group project for UCT's **ECO5040W: Financial Software
Engineering (FSE)**. A sender deposits ZAR, gets a quote, and sends money to a
beneficiary. RemitX settles each transfer by burning a stablecoin on chain,
then pays the beneficiary out in their own currency.

As a continuation of the FSE project, a **stokvel remittance** feature was
built on top of RemitX for the **ECO5037W (FTC)** class project. Its goal is
to remit each stokvel payout to a member's beneficiary. Members pay into a
smart contract each round, and each round's pool is sent through RemitX as a
remittance to the scheduled member's beneficiary in another country. The FTC
work changes parts of the original platform, most importantly moving
settlement off the XRP Ledger onto the XRPL EVM chain. See
[Stokvel remittance feature (FTC)](#stokvel-remittance-feature-ftc) and
[What changed for FTC](#what-changed-for-ftc).

> [!IMPORTANT]
> This is an academic prototype. It runs on the **XRPL EVM Testnet only**
> with synthetic users, test tokens and simulated fiat. No
> real customer funds, real remittances or production blockchain credentials are involved. Settlement
> uses **UCTUSD**, a lecturer-approved ERC-20 test token that stands in for
> RLUSD because the Testnet RLUSD faucet is rate-limited.

| Brief | Course |
|---|---|
| [docs/fse_project_brief.md](docs/fse_project_brief.md) | ECO5040W (FSE): the remittance platform |
| [docs/ftc_project_brief.md](docs/ftc_project_brief.md) | ECO5037W (FTC): the stokvel feature |

## How it works

1. **Sign up and verify.** A user signs up with Clerk, then completes a mock
   KYC application. The API validates identity documents by their leading
   bytes and stores them in private object storage. Compliance staff approve
   or reject each application in the admin portal. Only approved users can
   send.
2. **Deposit ZAR (simulated cash-in).** Every user gets their own payment
   reference, such as `sipho1-zar`. A treasury operator reconciles a bank
   statement against those references, which credits the sender's ZAR
   balance.
3. **Quote.** The sender picks a beneficiary and an amount. The quote freezes
   the exchange rate, fixed and percentage fees, FX margin, token amount,
   cash-out fee and estimated payout for 15 minutes. It is checked against
   the sender's daily and monthly limits.
4. **Confirm.** Confirming the quote writes every ledger leg of the transfer as
   `pending` in one commit. It then puts a settlement message on a Redis
   queue.
5. **Settle.** A Celery worker claims the transfer, burns the UCTUSD on the
   XRPL EVM Testnet, and stores the transaction hash. It then confirms every
   leg together, or fails them all together. Guarded status transitions mean a
   redelivered message never settles a transfer twice.
6. **Pay out and withdraw.** The beneficiary sees the payout in their own
   currency account. Either user can withdraw a fiat balance to a bank
   account, less a cash-out fee.

The double-entry ledger, the seven legs of a remittance, fees, precision and
open questions are all written up in
[docs/Transaction_Flow_Context.md](docs/Transaction_Flow_Context.md), which
records the platform as it was before the FTC work. The KYC risk scoring is in
[docs/kyc-risk-rules.md](docs/kyc-risk-rules.md).

## Stokvel remittance feature (FTC)

A stokvel is a rotating savings group: members contribute each round, and one
member receives the pool in turn. This feature remits that payout straight to
the member's beneficiary. A smart contract holds the contributions and
releases each pool only when its payout rules are met.

1. **Create.** A KYC-approved user creates a stokvel with a fixed UCTUSD
   contribution and becomes its **Organiser**.
2. **Invite.** The Organiser invites verified users, who join by accepting
   (up to three members in the prototype).
3. **Set up.** The Organiser enters the payout order the members agreed, and
   each member picks a cross-border **Payout beneficiary**.
4. **Start.** The Organiser sets the round schedule and starts the cycle,
   which is registered on the contract.
5. **Contribute.** Each round, members pay from their fiat account, plus an
   equal share of the payout remittance's fee and FX margin. The contract
   refuses duplicate payments.
6. **Release.** A round's pool is released once it and the next round are
   fully paid and its payout time has passed. Early releases are refused, and
   a round with an unpaid member stays blocked.
7. **Pay out.** RemitX remits the pool to the scheduled member's beneficiary
   and burns the UCTUSD. The member sees the status, hashes and remittance
   reference, and the beneficiary sees the payout come from the stokvel.
8. **Next cycle.** After the last round, members choose to continue or leave,
   and a new cycle starts.

Administrators can pause and resume the whole contract as an emergency stop.
Pausing halts contributions and releases for every stokvel but never bypasses
the release rules.

### On-chain

These are public testnet addresses, visible to anyone on the chain. No private
keys are listed here or committed to the repo.

| Item | Public address or value |
|---|---|
| Network | XRPL EVM Testnet, chain ID 1449000, RPC `https://rpc.testnet.xrplevm.org` |
| Stokvel contract | [`0x2f240705314BB79780522635eA47d20072CB8Fe1`](https://explorer.testnet.xrplevm.org/address/0x2f240705314BB79780522635eA47d20072CB8Fe1) (`StokvelVault`, one contract for every stokvel, source verified on [Sourcify](https://repo.sourcify.dev/1449000/0x2f240705314BB79780522635eA47d20072CB8Fe1)) |
| UCTUSD token | `0x7055071C7B79A859d9514e62833BFf041ce71074` (18 decimals) |
| Treasury Wallet | `0x6C350A0A9031DE51dF0535e2e88872Cd7330F2e7`: signs every contract call (members hold no keys) and receives released pools |

The contract relies on the backend to identify the contributing member: every
call comes from the Treasury Wallet, so the contract cannot tell who paid. See
[contracts/README.md](contracts/README.md#trust-assumption).

## What changed for FTC

- **XRP Ledger → XRPL EVM Testnet.** Settlement moved to the XRPL EVM chain
  (with lecturer approval), so the contract and the burn share one chain.
  UCTUSD is now an ERC-20 token.
- **Treasury Wallet.** One encrypted EVM wallet replaces the XRPL platform
  wallet, and the worker sends through web3.py instead of `xrpl-py`.
- **XRPL switched off, not deleted.** The XRPL code and settings stay in the
  repo, marked unused.
- **Smart contract.** The new `contracts/` folder holds `StokvelVault`, its
  tests, ABI and deploy scripts.
- **Worker schedule.** Scheduled tasks sync contract events and release rounds
  that are due.
- **Ledger.** A new `STOKVEL` account type holds each stokvel's pooled
  contributions.
- **Limits.** Stokvel contributions are checked against the member's monthly
  limit only.
- **Hosting.** Moved from Render to GCP (Cloud Run, Firebase Hosting,
  Upstash).

## Stack

| Layer | Technology |
|---|---|
| Smart contract | Solidity 0.8.24, OpenZeppelin Contracts v5, Hardhat |
| API | Python 3.11, FastAPI, SQLAlchemy, Alembic |
| Worker | Celery with a Redis broker and scheduled tasks, web3.py |
| Frontend | React Router v7 (SPA), Tailwind v4, shadcn/ui, Aceternity UI |
| API client | Generated by Hey API from [frontend/openapi.json](frontend/openapi.json) |
| Auth | Clerk |
| Database | Postgres (Neon in the cloud, Docker locally). SQLite for unit tests |
| KYC documents | S3-compatible object storage (Neon Object Storage in the cloud, MinIO locally) |
| Hosting | GCP Cloud Run (API and worker), Firebase Hosting (frontend), Upstash Redis, provisioned with Terraform |

## Repository layout

```
api/                 FastAPI app (remitx_api) and Celery worker (remitx_worker)
  alembic/           Database migrations
contracts/           StokvelVault contract, tests, ABI and deploy scripts (Hardhat)
frontend/            React Router SPA
infra/               Terraform for GCP and Neon (legacy Render under legacy-render/)
deploy/              Make targets for the Cloud Run and Firebase rollout
platform_wallet/     Scripts that create the Treasury Wallet, check balances and test a burn
tools/seeder/        Local-only QA test-data seeder (NiceGUI), with the stokvel demo
tools/loadtest/      Locust load test on a throwaway Docker stack
scripts/hooks/       Pre-commit hook implementations
docs/                Briefs, stokvel integration docs, deployment guide and ADRs
```

## Getting started: running locally

The app is already deployed: the FTC demo runs on QA at
[qa.remitx.tech](https://qa.remitx.tech), and production is at
[remitx.tech](https://remitx.tech) (see [Deployment](#deployment)). These
steps are only for running your own copy on your machine.

### Prerequisites

- Docker with Docker Compose
- Python 3.11 and Node 22, if you run the apps outside Docker
- A Clerk **development** application
- An [exchangerate-api.com](https://www.exchangerate-api.com) API key

### 1. Configure

A single root `.env` configures the API, the worker, the frontend and both
compose files. For local development you only need the values in
`.env.minimal.example`:

```bash
cp .env.minimal.example .env
```

Fill in `CLERK_SECRET_KEY`, `VITE_CLERK_PUBLISHABLE_KEY` and
`EXCHANGE_RATE_API_KEY`; the rest is pre-filled for the Docker stack. Every
other setting has a working default, and `.env.example` documents all of them.
Copy to `.env`, not `.env.local`: Vite would read `.env.local`, but the API and
compose would not.

### 2. Set up the Treasury Wallet (optional)

Without a wallet the app still runs, but anything on the blockchain won't
complete: transfers won't settle, and stokvel cycles, contributions and
payouts won't go through. To create one, run:

```bash
pip install -r platform_wallet/scripts/requirements.txt
python platform_wallet/scripts/create_evm_platform_wallet.py
```

It writes an encrypted key into `.env` and a plain-text backup to
`~/evm_platform_wallet.local.txt`; keep that backup and never commit it. Fund the
wallet with test XRP from the [XRPL EVM faucet](https://faucet.xrplevm.org)
and with UCTUSD. For stokvels, a new wallet also needs its own deployment of
the contract ([contracts/README.md](contracts/README.md#deploy)).

### 3. Run the stack

```bash
make up    # or: docker compose -f docker-compose.dev.yml up --build
```

This starts Postgres, Redis, MinIO, the API, the worker (with its beat
schedule for the stokvel tasks) and the frontend. A one-shot `migrate` service
applies the Alembic migrations first.

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API | http://localhost:4200 |
| API docs (Swagger UI) | http://localhost:4200/docs |
| MinIO console | http://localhost:9001 |

Stop it with `make down`.

To get from an empty database to a first deposit, see
[§9 of the transaction model](docs/Transaction_Flow_Context.md#9-seeding-a-fresh-local-database).
It predates FTC, so it still names the XRPL wallet, but the deposit steps are
the same.

The [QA seeder](tools/seeder/README.md) can populate a local database with
realistic users, KYC applications and transfers. With the stokvel scenario on,
it also sets up the FTC brief's three demo members, verified and funded, with
a stokvel ready for its cycle to start.

### Running the apps without Docker

```bash
make api-install        # api/.venv with dev tools
make api-migrate        # alembic upgrade head against DATABASE_URL
make api-dev            # http://localhost:4200

make frontend-install
make frontend-dev       # http://localhost:5173
```

Run `make` to list every shortcut.

## Development

### Tests and checks

```bash
make api-test           # pytest (in-memory SQLite)
make api-lint           # ruff check --fix + ruff format
make frontend-lint      # typecheck + prettier --check
make frontend-test      # vitest
make seeder-test        # needs SEEDER_TEST_DATABASE_URL

cd contracts && npm ci && npx hardhat test   # contract tests, hand-written and randomised
```

The Postgres-only tests, such as the row-lock tests, run when
`TEST_DATABASE_URL` is set:

```bash
cd api && TEST_DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@localhost:5432/postgres pytest -m postgres
```

### Git hooks

```bash
make hooks
```

The pre-commit hooks:

- regenerate `frontend/openapi.json` when the API changes
- run gitleaks, with custom rules for EVM private keys, XRPL seeds and database URLs
- block any `.env` file from being committed
- run ruff, pytest, prettier and the frontend typecheck
- run the Hardhat tests when `contracts/` changes

### Changing the API or the contract

- **API route changed:** run `make openapi` to regenerate
  `frontend/openapi.json`. The frontend client regenerates from it
  automatically. A test fails if it is stale.
- **Contract interface changed:** run `npm run export:abi` in `contracts/` and
  commit `contracts/abi/`. The
  deployed contract has to be redeployed, which changes its address
  ([contracts/README.md](contracts/README.md#deploy)).
- **Stokvel work:** record any new or changed features, endpoints, statuses,
  worker tasks or contract functions in
  [docs/stokvel_integration.md](docs/stokvel_integration.md), and add a row to
  [docs/stokvel_changelog.md](docs/stokvel_changelog.md) in the same PR.

[CLAUDE.md](CLAUDE.md) covers the API's layering (routes → controllers →
repositories → ORM), migration rules and frontend UI conventions.

### Load testing

```bash
make loadtest
```

This builds a throwaway stack, seeds it, runs Locust and writes a report to
`tools/loadtest/results/`. It never calls Clerk, the rate API or the chain:
the worker's burn is simulated. See
[tools/loadtest/README.md](tools/loadtest/README.md).

## Deployment

| Branch | Environment |
|---|---|
| `main` | QA ([qa.remitx.tech](https://qa.remitx.tech)): the FTC demo runs here |
| `stable` | Production ([remitx.tech](https://remitx.tech)) |

Feature branches target `main`. A release is a PR from `main` into `stable`.
GitHub Actions runs CI on every PR, including the contract tests when
`contracts/` changes. On a push to `main` or `stable`, it applies Terraform,
runs the migrations, and deploys the API and worker to Cloud Run and the
frontend to Firebase Hosting. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) and
[infra/README.md](infra/README.md).

## Security

- The Treasury Wallet's private key is Fernet-encrypted, with the decryption
  key held in a separate setting. Only the worker decrypts it. Keys are never
  returned by the API, logged or committed.
- The contract deployer's key stays in `contracts/.env` on the deployer's
  machine and is never loaded by the API. The contract admin and the operator
  must be different addresses, so the key that moves tokens cannot also
  control the emergency stop.
- Nothing personal goes on-chain. Stokvels and members are identified by
  per-stokvel database IDs, never user IDs, names or accounts.
- KYC documents live in a private bucket, never in Postgres. The API reads
  them through signed URLs that expire in minutes, and writes every read to the
  audit log.
- Staff access is role-based. Role changes, views of unmasked KYC details,
  contract pauses and manual releases are written to the audit log.

## Documentation

| Document | What it covers |
|---|---|
| [docs/fse_project_brief.md](docs/fse_project_brief.md) | The FSE brief (ECO5040W) |
| [docs/ftc_project_brief.md](docs/ftc_project_brief.md) | The FTC brief (ECO5037W) |
| [docs/Transaction_Flow_Context.md](docs/Transaction_Flow_Context.md) | The FSE platform's ledger model, remittance flow and fees, as before FTC |
| [docs/kyc-risk-rules.md](docs/kyc-risk-rules.md) | KYC risk scoring and tiers |
| [CONTEXT.md](CONTEXT.md) | Stokvel domain language: Stokvel, Organiser, Member, Administrator, cycles and rounds |
| [docs/stokvel_integration.md](docs/stokvel_integration.md) | Stokvel decisions, deviations from the brief, contract interface, worker tasks, REST API and progress |
| [docs/stokvel_database_model.md](docs/stokvel_database_model.md) | Stokvel tables, statuses and ledger changes |
| [docs/stokvel_changelog.md](docs/stokvel_changelog.md) | Changes to the stokvel docs |
| [docs/stokvel_test_plan.md](docs/stokvel_test_plan.md) | Stokvel test plan |
| [contracts/README.md](contracts/README.md) | The `StokvelVault` contract: rules, roles, developing and deploying |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | GCP, Neon and Clerk setup |
| [docs/adr/](docs/adr/) | Architecture decision records |
| [api/alembic/README.md](api/alembic/README.md) | Migration conventions |
| [frontend/README.md](frontend/README.md) | UI component standard and calling the API |
| [tools/seeder/README.md](tools/seeder/README.md) | QA seeder and the stokvel demo |
| [tools/loadtest/README.md](tools/loadtest/README.md) | Load test |
