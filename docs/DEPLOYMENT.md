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
env vars in step with the environment's secrets.

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
- **Celery not consuming:** confirm the worker web service is up (wake URL
  reachable) and `REDIS_URL` uses the shared Key Value with the right `/0` or
  `/1`.
- **750 instance-hours exhausted:** all free web services suspend until next
  month. Spun-down time does not count.
- **Custom domain verify failed:** DNS may still be propagating; retry in the
  Render dashboard.
