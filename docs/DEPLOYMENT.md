# RemitX cloud deployment (Azure + Neon + Clerk)

This guide covers the **Azure + Neon + Clerk** stack for QA (`main` branch) and Production (`stable` branch). Local development uses Docker Compose with Postgres + Redis + Celery — no cloud required day-to-day.

**Design spec:** [docs/superpowers/specs/2026-08-18-azure-neon-deployment-design.md](superpowers/specs/2026-08-18-azure-neon-deployment-design.md)

## Stack overview

| Component | QA | Production |
|-----------|-----|------------|
| Frontend | Azure Static Web Apps | Azure Static Web Apps |
| API | Azure Container Apps (scale to zero) | Azure Container Apps |
| Worker | Container Apps (always on) | Container Apps |
| Database | Neon branch `qa` | Neon branch `main` |
| Queue | Redis (internal Container App) | Redis (internal Container App) |
| Auth | Clerk QA app | Clerk Production app |
| Secrets | Azure Key Vault | Azure Key Vault |
| Region | `spaincentral` (default) | `spaincentral` |

## Prerequisites

1. **Personal Azure** pay-as-you-go subscription (Entra app registration for OIDC).
2. GitHub repository with Actions enabled.
3. **Neon** account — one project, branches for QA and Production.
4. Three **Clerk** applications: Development (local), QA, Production.
5. Docker locally for dev stack and container image builds.

## One-time bootstrap

### 1. Neon

1. Create a Neon project (e.g. `remitx`).
2. Create branches: **`qa`** (for git `main`) and **`main`** or **`production`** (for git `stable`).
   Neon branch names are independent of the git branch names.
3. Copy each branch connection string (`postgresql+psycopg2://…?sslmode=require`).

### 2. Terraform backend (Azure)

See [infra/README.md](../infra/README.md) — create `remitx-tfstate-rg` storage account once.

### 3. Azure OIDC for GitHub Actions

Register an Entra application with federated credentials for:

- `repo:<org>/RemitX:environment:qa`
- `repo:<org>/RemitX:environment:prod`

Grant **Contributor** on the subscription or resource groups. Store in GitHub:

| Secret / variable | Value |
|-------------------|--------|
| `AZURE_CLIENT_ID` | App (client) ID |
| `AZURE_TENANT_ID` | Directory tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Subscription ID |

### 4. GitHub environment secrets

Per **qa** and **prod** environments:

| Secret | Source |
|--------|--------|
| `TF_VAR_database_url` | Neon branch connection string |
| `MIGRATIONS_DATABASE_URL` | Neon connection string, SQLAlchemy format (`postgresql+psycopg2://…?sslmode=require`), used by the `migrate` job. Kept separate from `TF_VAR_database_url` so migrations can run as a role that owns the schema while the app runs as a more restricted one. If you are not doing that split yet, set both to the same value — but keep them in sync, or migrations and the app will target different databases. |
| `TF_VAR_clerk_secret_key` | Clerk dashboard |
| `TF_VAR_clerk_publishable_key` | Clerk dashboard |
| `TF_VAR_xrpl_encryption_key` | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `GHCR_PULL_TOKEN` | GitHub PAT with **`read:packages`** (Container Apps pull from private GHCR) |
| `VITE_API_URL` | `terraform output api_url` after first infra apply (e.g. `https://remitx-qa-api….azurecontainerapps.io`) |
| `VITE_SITE_URL` | Public frontend URL for Open Graph / social metadata (`https://qa.remitx.tech` for QA, `https://remitx.tech` for prod) |
| `VITE_CLERK_PUBLISHABLE_KEY` | Clerk publishable key (frontend build) |
| `AZURE_STATIC_WEB_APPS_API_TOKEN` | `terraform output -raw static_web_app_deployment_token` after SWA is created |

**Database migrations:** the `migrate` job in `deploy.yml` runs `alembic upgrade head` against Neon and gates `deploy-api` / `deploy-worker`, so a failed migration blocks the rollout instead of leaving a running app on a schema it does not match. If `MIGRATIONS_DATABASE_URL` is unset the job fails loudly rather than silently skipping. See [../api/alembic/README.md](../api/alembic/README.md).

**GHCR pull token:** GitHub → Settings → Developer settings → Personal access tokens → fine-grained or classic with `read:packages`. Username for GHCR is your GitHub username (owner of the repo).

**SWA deployment token:** after `terraform apply`:

```bash
cd infra/envs/qa
terraform output -raw static_web_app_deployment_token
```

Paste into GitHub **qa** environment secret `AZURE_STATIC_WEB_APPS_API_TOKEN`.

### 5. Deploy QA infrastructure

QA deploys from `main`, so merging a PR is all it takes:

```bash
git push origin main
```

Merge infra changes to `main` → `deploy.yml` runs `terraform apply`, then any changed app deploy jobs.

Then push API/worker/frontend changes to trigger the corresponding deploy jobs (Terraform runs first when `infra/**` changed in the same push).

## Branch model

| Git branch | Role | Deploys to | Protection |
|------------|------|-----------|------------|
| `main` | Quality assurance / integration. Default branch, always current. | QA stack (`qa` environment, `infra/envs/qa/`) | PR required, no force-push, no deletion |
| `stable` | Releases. Lags `main` and only moves on a deliberate promotion. | Production (`prod` environment, `infra/envs/prod/`) | PR required, no force-push, no deletion |

Feature branches target `main`. Releasing means opening a PR from `main` into
`stable`; merging it is what triggers a production deploy.

```bash
gh pr create --base stable --head main --title "Release: <summary>"
```

Note that the environment names (`qa`, `prod`), the Terraform roots, the Azure
resource names, the Neon branches, and the Clerk apps all keep their existing
names. Only the git branch that feeds each environment changed.

## CI/CD

| Workflow | Trigger | Action |
|----------|---------|--------|
| `ci.yml` | PR, push | pytest, ruff, `alembic upgrade head` + `alembic check` against a Postgres service, frontend lint/typecheck |
| `deploy.yml` | PR `infra/**`; push `main`/`stable` on `infra/**`, `api/**`, or `frontend/**` | Path-filtered pipeline: Terraform plan/apply → Alembic migrate → deploy API, worker, and/or frontend |

### `deploy.yml` job order

```text
changes
   └── ci
          └── terraform (if infra/** changed)
                 └── migrate (if api/** changed — alembic upgrade head against Neon)
                        ├── deploy-api      (if api/** changed, requires migrate success)
                        ├── deploy-worker   (if api/** changed, requires migrate success)
                        └── deploy-frontend (if frontend/** changed, migrate success or skipped)
```

CI must pass before Terraform, the migration, or any deploy job runs.
The standalone `ci.yml` workflow still runs on every PR and push for branch
protection; `deploy.yml` re-invokes it via `workflow_call` so deploy cannot
proceed on a failing commit.

`migrate` runs *before* the images roll out, so a failed migration blocks the
rollout instead of leaving a running app on a schema it does not match. The
corollary is that the currently-deployed app version keeps serving traffic
against the new schema until the rollout finishes — see rule 5 in
[../api/alembic/README.md](../api/alembic/README.md) for what that means when
writing a migration.

**A note on the `if` conditions.** Every dependent job starts with
`!cancelled()`. GitHub applies an implicit `success()` to any job `if` that has
no status-check function, and a *skipped* dependency fails that check just as a
failed one does — so without `!cancelled()`, any push that does not touch
`infra/**` would skip `terraform`, then silently skip every deploy job, and
still report the run green. Because `!cancelled()` also disables the implicit
CI gate, each job now checks `needs.ci.result == 'success'` explicitly.

## Local development

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up --build
```

Stack: Postgres, Redis, API, Celery worker, frontend. Celery broker: `REDIS_URL=redis://localhost:6379/0`.

Integration test with Redis:

```bash
cd api && SKIP_REDIS_TESTS=0 pytest tests/test_celery_ping.py -v
```

## Clerk

| Environment | Clerk application | Keys in |
|-------------|-------------------|---------|
| Local | Development | root `.env` |
| QA | QA | Key Vault + GitHub secrets for frontend |
| Prod | Production | Key Vault + GitHub secrets for frontend |

Configure allowed origins in the Clerk dashboard (not Terraform). Each
application needs the origins that will call it:

| Environment | Origins |
|-------------|---------|
| Development | `http://localhost:5173` |
| QA | `https://qa.remitx.tech` |
| Production | `https://remitx.tech` |

The API sends the same list to Clerk as `authorized_parties`, sourced from
`CORS_ORIGINS`. If an origin is missing from either side, verification fails
with a 401 that looks like a bad token rather than a misconfiguration.

**Removing a Key Vault secret:** deleting the `clerk_jwks_url` resource leaves
the secret soft-deleted in the vault rather than purged. That is expected and
harmless; it stays recoverable for the vault's retention period.

## Destroy (cost saving)

**Azure:**

```bash
cd infra/envs/qa && terraform destroy -var-file=non-secret.tfvars
cd infra/envs/prod && terraform destroy -var-file=non-secret.tfvars
```

**Neon:** delete branches/project in Neon console.

## Troubleshooting

- **API 502 / cold start:** Container Apps API scales to zero in QA; first request may take ~30s.
- **Celery not consuming:** Check worker Container App logs in Log Analytics; verify `REDIS_URL` in Key Vault.
- **Database connection:** Ensure Neon connection string includes `?sslmode=require` and IP allowlist allows Azure (Neon default allows all).
