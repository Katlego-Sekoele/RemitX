# Render Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move RemitX cloud compute to Render (Hobby/free) with Terraform IaC, keep Neon and Clerk, and preserve the GitHub CI → apply → migrate → deploy gate.

**Architecture:** Render free web services for API and worker (worker also serves `/health` and is woken via optional `WORKER_WAKE_URL`). One free Key Value shared across QA/Prod. Neon remains Postgres. HCP Terraform holds state. Azure Terraform is parked under `infra/legacy-azure/` for destroy.

**Tech Stack:** Terraform `render-oss/render`, HCP Terraform, FastAPI, Celery, React Router static site, GitHub Actions, Neon, Clerk.

## Global Constraints

- Render Hobby; `plan = free` on web services and Key Value.
- No `render_background_worker`; no Render Postgres.
- Auto-deploy off; Actions triggers deploys after migrate.
- `WORKER_WAKE_URL` empty ⇒ no HTTP wake.
- Production custom domains only: `remitx.tech`, `api.remitx.tech`.
- Region `frankfurt`. Python 3.11. XRPL Testnet only.

---

## File map

- Create: `infra/shared/*`, `infra/modules/{web_service,static_site,keyvalue}/*`, `infra/envs/{qa,prod}/*`, `infra/README.md`
- Park: `infra/legacy-azure/**`
- Modify: `api/Dockerfile`, `api/Dockerfile.worker`, `api/remitx_api/config.py`, `api/remitx_api/services/queue_service.py`, `api/remitx_worker/*`, `.github/workflows/deploy.yml`, `.env.example`, `docs/DEPLOYMENT.md`, `CLAUDE.md`
- Test: `api/tests/test_queue_wake.py`, `api/tests/test_worker_http.py`, `api/tests/test_reclaim.py`

## Tasks

### Task 1: Worker wake + reclaim + PORT image entrypoints

TDD on `queue_service.wake_worker`, reclaim of `PENDING` rows, and `/health` on the worker HTTP server. Dockerfiles run `python -m remitx_api` / `python -m remitx_worker`.

### Task 2: Terraform Render modules and env roots

Shared Key Value + project; QA/Prod web + static services; HCP backends; outputs for service IDs and DNS.

### Task 3: deploy.yml + docs

HCP + Render auth; apply shared then env; migrate unchanged; deploy via Render API; rewrite `docs/DEPLOYMENT.md`, `infra/README.md`, `CLAUDE.md`; Azure destroy runbook in `infra/legacy-azure/README.md`.
