# RemitX cloud deployment (GCP + Neon + Clerk)

This guide covers the **GCP + Upstash + Neon + Clerk** stack for QA (`main`
branch) and Production (`stable`). Local development uses Docker Compose with
Postgres + Redis + Celery — no cloud required day-to-day.

**Infrastructure:** [infra/README.md](../infra/README.md). Legacy Render:
[infra/legacy-render/](../infra/legacy-render/).

## Stack overview

| Component | QA | Production |
|-----------|-----|------------|
| Frontend | Firebase Hosting | Firebase Hosting → `remitx.tech` |
| API | Firebase Hosting → Cloud Run (`qa-api.remitx.tech`) | Firebase Hosting → Cloud Run (`api.remitx.tech`) |
| Worker | Cloud Run (HTTP + Celery) | Cloud Run |
| Database | Neon branch `qa` | Neon branch `main` |
| KYC documents | Neon Object Storage `remitx-qa-kyc-documents` | `remitx-prod-kyc-documents` |
| Queue | Upstash Redis (per env) | Upstash Redis |
| Auth | Clerk QA app | Clerk Production app |
| Secrets | GitHub Environment → Terraform / `gcloud run deploy` | same |
| GCP region | `africa-south1` (Johannesburg) | same |

Neon Postgres and object storage stay in **EU** (`eu-central-1` endpoints) per
Neon branch; only GCP compute and Artifact Registry use South Africa.

## Prerequisites

**Manual (one-time):** GCP project + billing, HCP Terraform org/workspaces, Neon
+ Upstash + Clerk accounts, GitHub environments `qa` and `prod`, DNS, and
**issuing** deploy credentials (JSON key or WIF) for the Terraform-managed
`remitx-github-deploy` SA. **Automated:** deploy SA + IAM, Artifact Registry,
Cloud Run, Firebase, Upstash DB, and most GCP config via Terraform +
`deploy.yml`.

Full checklists, job order, and every GitHub secret/variable name:
[infra/README.md](../infra/README.md) (sections *Manual vs automated* and
*GitHub environments catalog*).

**Existing Neon Postgres:** one-time import into TFC workspace `remitx-data` —
[infra/data/README.md](../infra/data/README.md) (Deploy does not run import).

## Branch model

| Git branch | Role | Deploys to |
|------------|------|-----------|
| `main` | QA / integration | `infra/gcp/` (workspace `remitx-gcp-qa`) |
| `stable` | Production | `infra/gcp/` (workspace `remitx-gcp-prod`) |

Feature branches target `main`. Releasing is a PR from `main` into `stable`.

## CI/CD

| Workflow | Trigger | Action |
|----------|---------|--------|
| `ci.yml` | PR, push | pytest, ruff, Alembic check, frontend lint/typecheck |
| `deploy.yml` | PR `infra/**`; push `main`/`stable` on `infra/**`, `api/**`, `frontend/**`, or the pipeline itself; manual `workflow_dispatch` | Neon storage verify → Terraform → Alembic migrate → Cloud Run + Firebase |

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

**Terraform runs on every rollout** (`infra/data` then `infra/gcp`), not only
when `infra/**` changed. PRs plan only; pushes and manual runs apply.

Every deploy job requires `terraform` to have **succeeded**. Rolling code onto
infrastructure that failed to converge is how a green run leaves a broken
environment.

**Migrate and all three deploys run on every rollout**, not only when
`api/**` or `frontend/**` changed. Alembic is a no-op at head. Cloud Run images
and env are updated by `.github/scripts/gcp-deploy-cloud-run.sh` (reads
Terraform outputs). The SPA is built with `VITE_*` from Terraform and deployed
via `.github/scripts/gcp-deploy-firebase.sh`.

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
`GET`s `WORKER_WAKE_URL` (the worker `/health`) if that variable is set. The
worker accepts that ping only from inside the VPC, so a cold Cloud NAT path
can take half a minute before the request arrives.
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

- **API or worker cold start:** Cloud Run scales to zero; first request (or
  `WORKER_WAKE_URL` ping) can take several seconds.
- **Celery not consuming:** check worker Cloud Run logs, `REDIS_URL` (Upstash),
  and that `WORKER_WAKE_URL` points at the worker `/health` URL.
- **Worker OOM:** lower `CELERY_CONCURRENCY` (Terraform sets `2`) or raise
  Cloud Run memory for the worker service.
- **KYC uploads 503:** Neon object storage verify failed or
  `OBJECT_STORAGE_*` secrets unset; see `scripts/neon-storage/README.md`.
- **Wrong database after deploy:** `remitx-data` overrides must not be fed from
  per-environment GitHub secrets on every rollout — use TFC workspace vars for
  `remitx-data` only.
- **Custom domain verify failed:** check Firebase Hosting / Cloud Run domain
  mapping and DNS records in Cloud DNS or your registrar.
