# RemitX cloud deployment (Render + Neon + Clerk)

This guide covers the **Render + Neon + Clerk** stack for QA (`main` branch)
and Production (`stable` branch). Local development uses Docker Compose with
Postgres + Redis + Celery — no cloud required day-to-day.

**Design spec:** [docs/superpowers/specs/2026-09-12-render-migration-design.md](superpowers/specs/2026-09-12-render-migration-design.md)

## Stack overview

| Component | QA | Production |
|-----------|-----|------------|
| Frontend | Render static site | Render static site → `remitx.tech` |
| API | Free web service (Docker) | Free web service → `api.remitx.tech` |
| Worker | Free web service (HTTP + Celery) | Free web service (HTTP + Celery) |
| Database | Neon branch `qa` | Neon branch `main` / `production` |
| Queue | Shared Key Value `/0` | Shared Key Value `/1` |
| Auth | Clerk QA app | Clerk Production app |
| Secrets | Render env vars via Terraform | same |
| Region | Frankfurt | Frankfurt |

Hobby limits that shape this stack: no free background worker (the worker is a
web service), one free Key Value per workspace, two included custom domains
(Production takes both). Neon is kept because free Render Postgres expires
in 30 days.

## Prerequisites

1. Render Hobby workspace + API key + owner id.
2. HCP Terraform org (name in `TF_CLOUD_ORGANIZATION`) with workspaces
   `remitx-shared`, `remitx-qa`, `remitx-prod`.
3. GitHub repository with Actions enabled.
4. Neon project with `qa` and `main` (or `production`) branches.
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
| `deploy.yml` | PR `infra/**`; push `main`/`stable` on `infra/**`, `api/**`, or `frontend/**` | Terraform → Alembic migrate → Render deploy |

### `deploy.yml` job order

```text
changes
   └── ci
          └── terraform (if infra/** changed)
                 └── migrate (if api/** changed)
                        ├── deploy-api
                        ├── deploy-worker
                        └── deploy-frontend
```

Auto-deploy is **off** on every Render service. Deploy jobs call
`.github/scripts/render-deploy.sh`, which looks up the service by name and
`POST`s a deploy. A failed migrate blocks API and worker rollouts.

## Worker wake

Free web services spin down after 15 minutes idle. After enqueue the API
`GET`s `WORKER_WAKE_URL` (the worker `/health`) if that variable is set.
Failures are logged and do not fail the API request. Unset the variable to
disable the ping (local Compose, or a future always-on worker).

On worker boot, `PENDING` integration messages are re-enqueued. That covers
a free Key Value restart wiping the broker. Settlement stays idempotent.

## Local development

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up --build
```

Do not set `WORKER_WAKE_URL` locally. The Compose worker runs Celery only.

## Clerk

| Environment | Clerk application | Origins |
|-------------|-------------------|---------|
| Local | Development | `http://localhost:5173` |
| QA | QA | the QA frontend `*.onrender.com` URL |
| Prod | Production | `https://remitx.tech` |

`CORS_ORIGINS` on the API must match. Terraform sets it from the frontend URL.

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
- **Celery not consuming:** confirm the worker web service is up (wake URL
  reachable) and `REDIS_URL` uses the shared Key Value with the right `/0` or
  `/1`.
- **750 instance-hours exhausted:** all free web services suspend until next
  month. Spun-down time does not count.
- **Custom domain verify failed:** DNS may still be propagating; retry in the
  Render dashboard.
