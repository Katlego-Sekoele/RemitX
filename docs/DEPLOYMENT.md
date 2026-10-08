# RemitX cloud deployment (Render + Neon + Clerk)

This guide covers the **Render + Neon + Clerk** stack for QA (`main` branch)
and Production (`stable` branch). Local development uses Docker Compose with
Postgres + Redis + Celery — no cloud required day-to-day.

**Design spec:** [docs/superpowers/specs/2026-09-12-render-migration-design.md](superpowers/specs/2026-09-12-render-migration-design.md)

## Stack overview

| Component | QA | Production |
|-----------|-----|------------|
| Frontend | Render static site | Render static site → `remitx.tech` |
| API | Free web service (Docker) | Free web service (`*.onrender.com`) |
| Worker | Free web service (HTTP + Celery) | Free web service (HTTP + Celery) |
| Database | Neon branch `qa` | Neon branch `main` / `production` |
| KYC documents | Neon Object Storage bucket `remitx-qa-kyc-documents` | Neon Object Storage bucket `remitx-prod-kyc-documents` |
| Queue | Shared Key Value `/0` | Shared Key Value `/1` |
| Auth | Clerk QA app | Clerk Production app |
| Secrets | Render env vars via Terraform | same |
| Region | Frankfurt | Frankfurt |

Hobby limits that shape this stack: no free background worker (the worker is a
web service), one free Key Value per workspace, two included custom domains
(Production `remitx.tech`, QA `qa.remitx.tech`). Neon is kept because free Render Postgres expires
in 30 days.

## Prerequisites

1. Render Hobby workspace + API key + owner id.
2. HCP Terraform org (name in `TF_CLOUD_ORGANIZATION`) with workspaces
   `remitx-shared`, `remitx-qa`, `remitx-prod`.
3. GitHub repository with Actions enabled.
4. Neon project with `qa` and `main` (or `production`) branches, and one
   private Object Storage bucket per environment.
5. Three Clerk applications: Development (local), QA, Production.

See [infra/README.md](../infra/README.md) for the secret list and first apply.

## Branch model

| Git branch | Role | Deploys to |
|------------|------|-----------|
| `main` | QA / integration | `infra/envs/qa/` |
| `stable` | Production | `infra/envs/prod/` |

Feature branches target `main`. Releasing is a PR from `main` into `stable`.

## CI/CD

| Workflow | Trigger | Action |
|----------|---------|--------|
| `ci.yml` | PR, push | pytest, ruff, Alembic check, frontend lint/typecheck |
| `deploy.yml` | PR `infra/**`; push `main`/`stable` on `infra/**`, `api/**`, `frontend/**`, or the pipeline itself; manual `workflow_dispatch` | Terraform → Alembic migrate → Render deploy |

### `deploy.yml` job order

```text
changes
   └── ci
          └── terraform                       (every rollout; plan-only on a PR)
                 └── migrate                  (every rollout)
                        ├── deploy-api
                        ├── deploy-worker
                        └── deploy-frontend
```

**Terraform runs on every rollout**, not only when `infra/**` changed. It is
declarative, so a run that changes nothing plans empty. Gating it on `infra/**`
made the stack impossible to create: the single push that introduced the Render
services had a red `ci`, so `terraform` was skipped, and every push afterwards
skipped it again on the paths filter while the deploy jobs kept looking for
services that had never been applied. Running it always also keeps the Render
env vars in step with the environment's secrets. Free web services cannot
be updated through the provider (`maintenance mode can only be configured
for non-free tier services`); `env_vars` are ignored on the resource and
synced after apply by `.github/scripts/render-sync-env.sh`.

Every deploy job requires `terraform` to have **succeeded**. Rolling code onto
infrastructure that failed to converge is how a green run leaves a broken
environment.

**Migrate and all three deploys run on every rollout**, not only when
`api/**` or `frontend/**` changed. Alembic is a no-op at head. Render
auto-deploy is off and Terraform sets `skip_deploy_after_service_update`,
so an infra-only change (CORS, env vars) never reaches a running service
unless these jobs trigger a deploy.

Auto-deploy is **off** on every Render service. Deploy jobs call
`.github/scripts/render-deploy.sh`, which resolves the service by exact name,
`POST`s a deploy, and then **waits for that deploy to reach `live`** — a
`build_failed` on Render fails the job rather than passing silently. It checks
the HTTP status of every Render API call, so a rejected key reports itself
instead of looking like a missing service. Knobs: `RENDER_DEPLOY_WAIT=false` to
trigger and exit, `RENDER_DEPLOY_TIMEOUT_SECONDS` (default 1800),
`RENDER_DEPLOY_POLL_SECONDS`, `RENDER_DEPLOY_MAX_POLL_ERRORS`.

A failed migrate blocks every rollout.

### Manual rollout

Run **Actions → Deploy → Run workflow** against `main` (QA) or `stable`
(Production). A manual run treats everything as changed: it applies Terraform
and then deploys all three services. Use it to bootstrap a fresh environment,
or to reconcile after a red run, without having to push a commit.

A push that only touches the pipeline or docs runs `terraform` but no deploy
jobs — there is no new application code to roll out. Use a manual run if you
want the services redeployed as well.

## XRPL EVM Treasury Wallet

On-chain settlement is moving from the **XRP Ledger Testnet** to the **XRPL EVM
Testnet** (chain id `1449000`, Testnet only); the XRPL settings stay deployed
only until that move is done. The Treasury Wallet is an EVM address there,
holding UCTUSD as an ERC-20 and paying gas in test XRP. It is created by
`platform_wallet/scripts/create_evm_platform_wallet.py`.

| Setting | Secret? | Reaches |
|---------|---------|---------|
| `EVM_ENCRYPTION_KEY` | yes | worker only |
| `EVM_TREASURY_KEY_ENCRYPTED` | yes | worker only |
| `EVM_TREASURY_ADDRESS` | no | API and worker |
| `EVM_RPC_URL`, `EVM_CHAIN_ID`, `EVM_EXPLORER_URL` | no | API and worker |
| `UCTUSD_CONTRACT_ADDRESS`, `UCTUSD_EVM_DECIMALS` | no | API and worker |

Each is a Terraform input from the matching `TF_VAR_*` GitHub environment
secret or variable (see [infra/README.md](../infra/README.md)). All are
optional for now: an unset one is left out of the service's environment, and
the secrets are added to the worker only once they are set. Only the worker
decrypts the key and signs (`api/remitx_worker/evm_service.py`); the API's
`Config` has no setting for either secret.

## Object storage (KYC documents)

Uploaded identity documents are bytes, and bytes do not belong in Postgres — a
database dump taken to debug something should not contain a stranger's
passport. They go to **Neon Object Storage**, which speaks S3, so the same code
runs against MinIO locally and no second SDK exists in the codebase.

**Create one private bucket per environment** (Neon console → Object Storage,
or the Neon API), then a key pair scoped to it:

| Setting | QA | Production |
|---------|-----|-----------|
| `OBJECT_STORAGE_BUCKET` | `remitx-qa-kyc-documents` | `remitx-prod-kyc-documents` |
| `OBJECT_STORAGE_ENDPOINT_URL` | the bucket's S3 endpoint | the bucket's S3 endpoint |
| `OBJECT_STORAGE_REGION` | `eu-central-1` | `eu-central-1` |
| `OBJECT_STORAGE_ACCESS_KEY_ID` | bucket key | bucket key |
| `OBJECT_STORAGE_SECRET_ACCESS_KEY` | bucket secret | bucket secret |

The endpoint, bucket and region are non-secret and live in
`infra/envs/<env>/non-secret.tfvars`. The two credentials are Terraform inputs
passed from the matching GitHub environment secrets
(`TF_VAR_object_storage_access_key_id`,
`TF_VAR_object_storage_secret_access_key`) and reach only the **API** service —
the worker never touches documents, so the bucket credential stays out of its
environment.

They are deliberately optional: with them unset the API starts normally and
only the KYC document routes answer `503`. Nothing else in the platform
depends on the bucket.

**The bucket must stay private.** Nothing is ever served from it directly, and
nothing writes to it but the API.

Uploads are POSTed to the API, which holds the bytes, identifies the file by
its leading bytes, hashes it and only then writes the object — so nothing
reaches the bucket that has not been checked. The body is capped while it
arrives, at the route and again in `MaxBodySizeMiddleware`, so an oversized
upload costs the bytes already read and nothing more.

Reads are the exception, for a mechanical reason: a document is rendered in
the reviewer's browser by an `<img>` or a sandboxed `<iframe>`, and neither
can carry an `Authorization` header, so serving those bytes through the API
would mean inventing a signed-URL scheme of our own. They use the bucket's —
five minutes, audited on issue. An identity document reachable by anyone
holding a URL is the single worst outcome available here.

**No CORS configuration is needed,** on the bucket or on MinIO. Uploads go to
the API, which is already an allowed origin, and `<img>`/`<iframe>` reads are
not CORS requests. That is worth noting because bucket CORS is the classic
failure here: it surfaces as an opaque network error rather than as anything
that names the cause.

**No virus scanning.** Uploads are type-checked by their leading bytes and
size-capped, and nothing executable or scriptable is accepted — but nothing
scans them for malware. Object-storage malware scanning is the real answer and
is out of scope for this project.

**Retention.** FICA §23 record-keeping runs five years from the end of the
relationship, so deleting an application does not delete its documents and no
route offers to. A lifecycle rule on the bucket is where that expiry would
eventually live.

## Worker wake

Free web services spin down after 15 minutes idle. After enqueue the API
`GET`s `WORKER_WAKE_URL` (the worker `/health`) if that variable is set.
Unset the variable to disable the ping (local Compose, or a future always-on
worker).

Ordering is the point: `send_task` is synchronous and raises if the broker
cannot be reached, so the message is on Redis before anything is pinged, and
a publish that fails pings nothing. The ping itself runs on a background
thread and only logs on failure — a cold instance answers 502 while it boots,
and a task already on Redis is not lost by a ping that did not land. Waking
is what the request must not wait for: a burst of five enqueues against a
4-second cold instance returns in 0.13 s and sends one ping, because wakes
collapse while one is outstanding (the booting worker drains the whole queue
regardless).

On worker boot, `PENDING` integration messages are re-enqueued. That covers
a free Key Value restart wiping the broker. Settlement stays idempotent.

## Local development

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up --build
```

Do not set `WORKER_WAKE_URL` locally. The Compose worker runs Celery only.

The stack includes **MinIO** (S3-compatible, console on
`http://localhost:9001`) and a one-shot job that creates the private
`kyc-documents` bucket, so the whole KYC document flow runs with no Neon
account. The API signs *read* URLs for `http://localhost:9000` — the host the
browser uses — while talking to MinIO at `http://minio:9000` itself; the host
is part of the SigV4 signature, so signing for the wrong one fails with a bare
403.

## Clerk

| Environment | Clerk application | Origins |
|-------------|-------------------|---------|
| Local | Development | `http://localhost:5173` |
| QA | QA | `https://qa.remitx.tech` and the QA frontend `*.onrender.com` URL |
| Prod | Production | `https://remitx.tech` and the prod frontend `*.onrender.com` URL |

`CORS_ORIGINS` on the API must include every browser origin that hosts the
frontend. Terraform sets it to the custom domain (when configured) and the
`*.onrender.com` URL so neither origin is rejected.

## Destroy Azure (one-time)

```bash
cd infra/legacy-azure/envs/qa && terraform destroy -var-file=non-secret.tfvars
cd infra/legacy-azure/envs/prod && terraform destroy -var-file=non-secret.tfvars
```

Do **not** delete the Neon project. Then delete Azure resource groups, the
tfstate storage account, Entra OIDC, and leftover Azure/SWA/GHCR GitHub
secrets. Details: [infra/legacy-azure/README.md](../infra/legacy-azure/README.md).

## Troubleshooting

- **API or worker ~1 minute delay:** free instance spinning up after idle.
- **Terraform `maintenance mode can only be configured for non-free tier
  services`:** provider bug on free web services. Env and custom-domain
  updates are ignored on `render_web_service`; env vars sync via
  `render-sync-env.sh` after apply. Change custom domains in the dashboard.
- **Celery not consuming:** confirm the worker web service is up (wake URL
  reachable) and `REDIS_URL` uses the shared Key Value with the right `/0` or
  `/1`.
- **Worker restart loop, "Ran out of memory (used over 512MB)", wake URL
  502s:** the pool is too wide for the instance. The worker banner prints its
  own `concurrency: N (prefork)`; each process imports `remitx_api` and costs
  roughly 100 MB, so N=8 needs ~925 MB against a 512 MB cap. A worker killed
  this way dies between `mingle: all alone` and `celery@... ready` — the
  absence of a `ready` line is the tell, and it means no task was ever
  consumed and the boot-time `PENDING` reclaim never ran. `CELERY_CONCURRENCY`
  sets N (Terraform pins it to 2); lower it to 1 for more headroom.
- **750 instance-hours exhausted:** all free web services suspend until next
  month. Spun-down time does not count.
- **Custom domain verify failed:** DNS may still be propagating; retry in the
  Render dashboard.
