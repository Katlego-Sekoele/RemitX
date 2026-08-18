# Azure + Neon Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate RemitX cloud from AWS CDK to Azure Container Apps + Neon Postgres + Clerk, with local/cloud Redis+Celery parity.

**Architecture:** Terraform provisions Azure (SWA, ACA API/worker/Redis, Key Vault). Neon branches supply Postgres. GitHub Actions OIDC deploys infra and app images to GHCR/ACA.

**Tech Stack:** Terraform (Azure), Neon, Clerk, GitHub Actions, Docker Compose, Celery, Redis.

## Global Constraints

- XRPL Testnet only; encrypted keys in Key Vault, never in API responses.
- Local and cloud both use Celery + Redis (no RabbitMQ).
- Neon connection strings manual bootstrap → Key Vault via `TF_VAR_database_url`.
- Clerk dashboard-managed (no Terraform Clerk provider).
- Python 3.9-compatible API code.

---

### Task 1: Destroy AWS CDK stacks — DONE

- [x] `cdk destroy RemitXQa RemitXGitHubOidc RemitXShared`
- [x] Delete orphan ECR `remitx-api-qa`

### Task 2: Revert local Redis parity — DONE

- [x] `docker-compose.dev.yml` — Redis replaces RabbitMQ
- [x] `api/remitx_worker/celery_app.py` — `REDIS_URL`
- [x] `.env.example`, `config.py`, `test_celery_ping.py`

### Task 3: Remove AWS artifacts; restore Terraform — DONE

- [x] Delete `infra/cdk/`, Lambda handler, `deploy-aws.yml`
- [x] Restore Terraform from PR #1; remove `postgresql` and `clerk` modules
- [x] Wire `var.database_url` (Neon) into Key Vault

### Task 4: Restore GitHub Actions + docs — DONE

- [x] Restore `terraform-qa.yml`, `terraform-prod.yml`, deploy workflows
- [x] Update workflows: `TF_VAR_database_url` (drop postgres/clerk_api_key)
- [x] Rewrite `docs/DEPLOYMENT.md`, `CLAUDE.md`, `infra/README.md`

### Task 5: Azure + Neon bootstrap (manual — user)

- [ ] Create Neon project + `qa` / `main` branches; save connection strings
- [ ] Bootstrap Terraform backend (`remitx-tfstate-rg`)
- [ ] Register Entra OIDC app; configure GitHub `qa`/`prod` environment secrets
- [ ] Push to `qa` → `terraform-qa.yml` applies QA stack
- [ ] Push API/worker/frontend → deploy workflows; verify `/health`

### Task 6: Production (after QA validated)

- [ ] Merge `qa` → `main`; `terraform-prod.yml` applies prod stack
- [ ] Configure Clerk Production allowed origins
- [ ] Optional: custom domains via `api_custom_domain` / `swa_custom_domain`

---

**Spec:** [2026-08-18-azure-neon-deployment-design.md](../specs/2026-08-18-azure-neon-deployment-design.md)
