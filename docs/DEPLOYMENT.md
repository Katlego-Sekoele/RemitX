# RemitX cloud deployment (Azure + Neon + Clerk)

This guide covers the **Azure + Neon + Clerk** stack for QA (`qa` branch) and Production (`main`). Local development uses Docker Compose with Postgres + Redis + Celery — no cloud required day-to-day.

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
2. Create branches: **`qa`** (for git `qa`) and **`main`** or **`production`** (for git `main`).
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
| `AZURE_DEPLOYER_OBJECT_ID` | GitHub environment **variable** — SP object ID for Key Vault |

### 4. GitHub environment secrets

Per **qa** and **prod** environments:

| Secret | Source |
|--------|--------|
| `TF_VAR_database_url` | Neon branch connection string |
| `TF_VAR_clerk_secret_key` | Clerk dashboard |
| `TF_VAR_clerk_publishable_key` | Clerk dashboard |
| `TF_VAR_clerk_jwks_url` | Clerk dashboard |
| `TF_VAR_xrpl_encryption_key` | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `VITE_API_URL` | Container App API FQDN after first deploy |
| `VITE_CLERK_PUBLISHABLE_KEY` | Clerk publishable key (frontend build) |
| `AZURE_STATIC_WEB_APPS_API_TOKEN` | From `terraform output` after SWA is created |

### 5. Deploy QA infrastructure

```bash
git checkout -b qa   # if not exists
git push origin qa
```

Merge infra changes to `qa` → `terraform-qa.yml` runs `terraform apply`.

Then push API/worker/frontend changes to trigger deploy workflows.

## CI/CD

| Workflow | Trigger | Action |
|----------|---------|--------|
| `ci.yml` | PR, push | pytest, ruff, frontend lint/typecheck |
| `terraform-qa.yml` | push `qa`, `infra/**` | Terraform plan/apply QA |
| `terraform-prod.yml` | push `main`, `infra/**` | Terraform plan/apply Prod |
| `deploy-api.yml` | push `qa`/`main`, `api/**` | GHCR push + Container App update |
| `deploy-worker.yml` | push `qa`/`main`, `api/**` | GHCR worker image + update |
| `deploy-frontend.yml` | push `qa`/`main`, `frontend/**` | SPA build → Static Web Apps |

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

Configure allowed origins in the Clerk dashboard (not Terraform).

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
