# AWS Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Vercel cloud stack with AWS (S3/CloudFront SPA, Lambda Flask API, Aurora Serverless v2, shared EC2 RabbitMQ + Celery, CDK, GitHub Actions) while keeping Docker Compose as the local dev path.

**Architecture:** Three CDK stacks — `SharedStack` (VPC, Aurora cluster with `remitx_qa` + `remitx_prod`, EC2 RabbitMQ + Celery workers), `QaStack` / `ProdStack` (Lambda, S3, CloudFront, SSM, logs). Lambda in VPC publishes Celery tasks to RabbitMQ; workers on EC2 consume. Clerk auth unchanged.

**Tech Stack:** AWS CDK (Python), Lambda container + Mangum, Aurora PostgreSQL Serverless v2, EC2 (t4g.small), RabbitMQ, Celery, Flask, React Router SPA, GitHub Actions OIDC, SSM SecureString, CloudWatch.

## Global Constraints

- XRPL **Testnet only**; no mainnet credentials in any environment.
- XRPL private keys encrypted in DB; encryption key in SSM, never returned by API or committed.
- Settlement async via **Celery + RabbitMQ** with duplicate-message protection (idempotent consumer + optional `task_id`).
- **One Aurora cluster**, databases **`remitx_qa`** and **`remitx_prod`** (not two schemas in one DB).
- **One EC2** RabbitMQ host; vhosts **`remitx-qa`** and **`remitx-prod`**.
- Default AWS region: **`af-south-1`** (override via CDK context if account lacks it).
- Secrets in **SSM Parameter Store SecureString**; never commit `.env` or secret values.
- Python **3.9+** compatible API code (ruff `py39`); Docker images may use 3.11.
- Clerk for auth (not Cognito).

---

## File map (created / modified / removed)

| Path | Responsibility |
|------|----------------|
| `infra/cdk/app.py` | CDK app entry; wires Shared + Qa + Prod + OIDC stacks |
| `infra/cdk/stacks/shared_stack.py` | VPC, Aurora cluster + DBs, EC2 broker/workers, shared SGs |
| `infra/cdk/stacks/env_stack.py` | Per-env Lambda, S3, CloudFront, SSM params, log groups |
| `infra/cdk/stacks/github_oidc_stack.py` | GitHub Actions IAM role |
| `infra/cdk/user_data/` | EC2 bootstrap: RabbitMQ Docker, systemd Celery units |
| `api/lambda_handler.py` | Mangum handler for Lambda |
| `api/Dockerfile.lambda` | Lambda container image |
| `api/remitx_worker/celery_app.py` | AMQP broker (replace Redis) |
| `docker-compose.dev.yml` | RabbitMQ replaces Redis |
| `frontend/react-router.config.ts` | `ssr: false` SPA mode |
| `.github/workflows/deploy-aws.yml` | CDK deploy + SPA sync + ECR push |
| `docs/DEPLOYMENT.md` | AWS setup guide (replaces Vercel) |
| **Remove:** `vercel/`, `worker/`, `scripts/cloud/`, `scripts/vercel/`, `.github/workflows/deploy-vercel.yml` | Superseded |

---

### Task 1: Local RabbitMQ + Celery migration

**Files:**
- Modify: `api/remitx_worker/celery_app.py`
- Modify: `docker-compose.dev.yml`
- Modify: `.env.example`
- Modify: `api/pyproject.toml` (add `kombu` if needed; remove Redis-only assumption)
- Modify: `api/tests/test_celery_ping.py`
- Delete or update: Redis-specific test skips

**Interfaces:**
- Produces: `celery` app with `broker=` AMQP URL from `CELERY_BROKER_URL` env (fallback `amqp://guest:guest@localhost:5672//`)

- [ ] **Step 1: Update Celery broker config**

```python
# api/remitx_worker/celery_app.py
import os
from celery import Celery

broker_url = os.getenv(
    "CELERY_BROKER_URL",
    "amqp://guest:guest@localhost:5672//",
)
celery = Celery("remitx_worker", broker=broker_url, backend=None)
celery.conf.task_default_queue = "settlement"
celery.conf.task_acks_late = True
celery.conf.result_backend = None
celery.autodiscover_tasks(["remitx_worker"])
```

- [ ] **Step 2: Replace Redis with RabbitMQ in Compose**

In `docker-compose.dev.yml`:
- Remove `redis` service and `redis_data` volume.
- Add:

```yaml
  rabbitmq:
    image: rabbitmq:3-management-alpine
    ports:
      - "${RABBITMQ_PORT:-5672}:5672"
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  worker:
    environment:
      CELERY_BROKER_URL: amqp://guest:guest@rabbitmq:5672//
    depends_on:
      rabbitmq:
        condition: service_healthy
```

- Update `api` service: remove `REDIS_URL`, add `CELERY_BROKER_URL`, depend on `rabbitmq`.

- [ ] **Step 3: Update `.env.example`**

Replace `REDIS_URL` / Upstash / QStash blocks with:

```bash
RABBITMQ_PORT=5672
CELERY_BROKER_URL=amqp://guest:guest@localhost:5672//
```

- [ ] **Step 4: Run tests**

```bash
cd api && pip install -e '.[dev]' && pytest -q
```

Expected: all pass (update `test_celery_ping` if broker connection mocked).

- [ ] **Step 5: Smoke-test Compose**

```bash
docker compose -f docker-compose.dev.yml up --build
# In another shell:
cd api && celery -A remitx_worker.celery_app inspect ping
```

Expected: `pong` from worker.

---

### Task 2: Lambda handler + container image

**Files:**
- Create: `api/lambda_handler.py`
- Create: `api/Dockerfile.lambda`
- Modify: `api/pyproject.toml` (add `mangum` dependency)

**Interfaces:**
- Produces: `handler` — Mangum ASGI/WSGI adapter around Flask `app` from `create_app()`

- [ ] **Step 1: Add Mangum dependency**

```toml
# api/pyproject.toml dependencies
"mangum>=0.17.0",
```

- [ ] **Step 2: Create handler**

```python
# api/lambda_handler.py
from mangum import Mangum

from remitx_api import create_app

app = create_app()
handler = Mangum(app.wsgi_app, lifespan="off")
```

- [ ] **Step 3: Create Dockerfile.lambda**

```dockerfile
FROM public.ecr.aws/lambda/python:3.11

COPY pyproject.toml .
COPY remitx_api/ remitx_api/
COPY remitx_worker/ remitx_worker/
COPY lambda_handler.py .

RUN pip install --upgrade pip && pip install .

CMD ["lambda_handler.handler"]
```

- [ ] **Step 4: Local import check**

```bash
cd api && pip install -e '.[dev]' && python -c "from lambda_handler import handler; print(handler)"
```

Expected: no import error.

---

### Task 3: CDK project scaffold

**Files:**
- Create: `infra/cdk/cdk.json`
- Create: `infra/cdk/requirements.txt`
- Create: `infra/cdk/app.py`
- Create: `infra/cdk/config.py` (region, env names, GitHub repo)
- Create: `infra/README.md`

**Interfaces:**
- Produces: CDK app synthesizing `SharedStack`, `QaStack`, `ProdStack`, `GitHubOidcStack`

- [ ] **Step 1: Create `infra/cdk/requirements.txt`**

```
aws-cdk-lib>=2.150.0
constructs>=10.0.0
```

- [ ] **Step 2: Create `infra/cdk/app.py`**

Wire stacks with context `environment=qa|prod`, default region `af-south-1`:

```python
#!/usr/bin/env python3
import aws_cdk as cdk
from stacks.shared_stack import SharedStack
from stacks.env_stack import EnvStack
from stacks.github_oidc_stack import GitHubOidcStack

app = cdk.App()
env = cdk.Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region") or "af-south-1",
)

shared = SharedStack(app, "RemitXShared", env=env)
oidc = GitHubOidcStack(app, "RemitXGitHubOidc", env=env)
EnvStack(app, "RemitXQa", environment_name="qa", shared=shared, env=env)
EnvStack(app, "RemitXProd", environment_name="prod", shared=shared, env=env)

app.synth()
```

- [ ] **Step 3: Verify synth (no deploy yet)**

```bash
cd infra/cdk && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cdk synth --context account=123456789012
```

Expected: CloudFormation templates for four stacks.

---

### Task 4: SharedStack — VPC, Aurora, EC2 broker

**Files:**
- Create: `infra/cdk/stacks/shared_stack.py`
- Create: `infra/cdk/stacks/__init__.py`
- Create: `infra/cdk/user_data/broker.sh`

**Interfaces:**
- Produces: CloudFormation exports / SSM params:
  - `/remitx/shared/vpc-id`
  - `/remitx/shared/aurora-endpoint`
  - `/remitx/shared/broker-private-ip`
  - `/remitx/shared/lambda-sg-id`
  - `/remitx/shared/ec2-sg-id`
- Creates Aurora cluster `remitx` with databases `remitx_qa`, `remitx_prod` (via `aws_rds.DatabaseCluster` + `CfnDBCluster` or cluster with default DB + custom resource for second DB)

- [ ] **Step 1: VPC** — 2 AZs, public + private subnets, NAT (single NAT for cost).

- [ ] **Step 2: Aurora Serverless v2** — one cluster, engine POSTGRES, min ACU 0.5, databases:
  - Use `rds.CfnDBCluster` + `rds.CfnDBInstance` or `DatabaseCluster` with `default_database_name="remitx_qa"` and **`AwsCustomResource`** to `CREATE DATABASE remitx_prod` via RDS Data API or Lambda on create (document in README).

- [ ] **Step 3: EC2** — `t4g.small`, Amazon Linux 2023 ARM, private subnet, SSM role, user-data runs `broker.sh`:
  - Docker install
  - `docker run -d rabbitmq:3-management` with persistent volume
  - Create vhosts `remitx-qa`, `remitx-prod` via `rabbitmqctl`
  - Install Python venv + `pip install -e` from S3 artifact or git pull (initial plan: **SSM Parameter** with S3 path to worker code tarball updated by CI — or bake AMI later; MVP: user-data clones repo branch is NOT acceptable; **CI rsyncs worker code to S3**, user-data pulls on boot)

- [ ] **Step 4: Security groups** — EC2 SG allows 5672 from Lambda SG; Lambda SG allows egress to EC2 + Aurora.

- [ ] **Step 5: `cdk synth` passes**

---

### Task 5: EnvStack — Lambda, S3, CloudFront

**Files:**
- Create: `infra/cdk/stacks/env_stack.py`

**Interfaces:**
- Consumes: SharedStack exports (VPC, SGs, Aurora endpoint, broker IP)
- Produces per env (`qa` / `prod`):
  - Lambda (image from ECR tag `remitx-api-{env}:latest`)
  - Function URL with CORS
  - S3 bucket + CloudFront distribution (OAC)
  - SSM params under `/remitx/{env}/` (placeholder SecureStrings for manual fill or CDK-generated secrets)
  - CloudWatch log group `/aws/lambda/remitx-api-{env}`

- [ ] **Step 1: Lambda** in VPC private subnets; env vars from SSM at deploy (CDK `StringParameter.value_for_string_parameter` or dynamic reference).

- [ ] **Step 2: Build `DATABASE_URL`** in CDK or store full URL in SSM after Aurora create:

```text
postgresql+psycopg2://user:pass@{aurora-endpoint}:5432/remitx_qa?sslmode=require
```

- [ ] **Step 3: S3 + CloudFront** — SPA error routing (`403/404 → index.html`).

- [ ] **Step 4: Output** Function URL and CloudFront domain as stack outputs.

---

### Task 6: GitHub OIDC stack

**Files:**
- Create: `infra/cdk/stacks/github_oidc_stack.py`

- [ ] **Step 1: OIDC provider** for `token.actions.githubusercontent.com` (if not exists).

- [ ] **Step 2: IAM role** trust policy: repo `Katlego-Sekoele/RemitX`, branches `qa` and `main`.

- [ ] **Step 3: Policies** — `cdk deploy`, ECR push, S3 sync to frontend buckets, PassRole for Lambda.

- [ ] **Step 4: Output role ARN** for GitHub secret `AWS_ROLE_ARN`.

---

### Task 7: Frontend SPA mode

**Files:**
- Modify: `frontend/react-router.config.ts`
- Modify: `frontend/vite.config.ts` (remove `@vercel/react-router` preset if present)
- Remove: `frontend/vercel.json`

- [ ] **Step 1: Disable SSR**

```typescript
// frontend/react-router.config.ts
export default { ssr: false } satisfies Config
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm ci && npm run build
```

Expected: static output under `frontend/build/client`.

- [ ] **Step 3: `npm run lint` passes**

---

### Task 8: GitHub Actions — deploy-aws.yml

**Files:**
- Create: `.github/workflows/deploy-aws.yml`
- Remove: `.github/workflows/deploy-vercel.yml`

- [ ] **Step 1: Workflow on push `qa` / `main`**

Jobs:
1. Reuse `ci.yml` (tests)
2. `deploy-shared` — only on `main` when `infra/cdk/**` changes (optional manual workflow_dispatch for first run)
3. `deploy-env`:
   - Configure AWS creds via OIDC
   - Build + push Lambda image to ECR
   - Build SPA with `VITE_API_URL` from stack output (or SSM)
   - `aws s3 sync frontend/build/client s3://$BUCKET --delete`
   - `cdk deploy RemitXQa` or `RemitXProd --require-approval never`
   - Invalidate CloudFront

- [ ] **Step 2: Document required GitHub secrets/vars**

`AWS_ROLE_ARN`, `AWS_REGION`, Clerk publishable keys per env.

---

### Task 9: EC2 Celery systemd units

**Files:**
- Create: `infra/cdk/user_data/celery-qa.service`
- Create: `infra/cdk/user_data/celery-prod.service`
- Modify: `infra/cdk/user_data/broker.sh` to install units

- [ ] **Step 1: Unit template** — reads env from `/etc/remitx/qa.env` (populated by script fetching SSM on boot and on timer).

- [ ] **Step 2: ExecStart**

```ini
ExecStart=/opt/remitx/venv/bin/celery -A remitx_worker.celery_app worker --loglevel=info -Q settlement
EnvironmentFile=/etc/remitx/qa.env
```

- [ ] **Step 3: Document manual SSM population** for broker URLs and DB URLs in `infra/README.md`.

---

### Task 10: Remove Vercel artifacts + update docs

**Files:**
- Delete: `vercel/`, `worker/`, `scripts/cloud/`, `scripts/vercel/`, `api/vercel.json`, `frontend/vercel.json`, Vercel worker modules (`api/remitx_worker/runner.py`, `cron_app.py`, `routes.py`) if only used for Vercel cron
- Rewrite: `docs/DEPLOYMENT.md`, `CLAUDE.md`
- Modify: `.gitignore` (remove Vercel-specific; add `infra/cdk/cdk.out/`)

- [ ] **Step 1: Delete superseded paths**

- [ ] **Step 2: Write `docs/DEPLOYMENT.md`** — bootstrap: `cdk bootstrap`, deploy Shared → Qa/Prod, populate SSM, Clerk apps, destroy order.

- [ ] **Step 3: Update `CLAUDE.md`** — AWS stack summary, remove Vercel references.

---

## Spec coverage checklist

| Spec requirement | Task |
|------------------|------|
| S3 + CloudFront SPA | 7, 5, 8 |
| Lambda + Function URL Flask | 2, 5, 8 |
| Aurora one cluster, two DBs | 4 |
| RabbitMQ EC2 shared | 4, 9 |
| Celery workers EC2 | 9 |
| Celery + RabbitMQ local | 1 |
| SSM SecureString | 5, 6, 9 |
| CloudWatch | 5, 9 |
| CDK Python | 3, 4, 5, 6 |
| GitHub Actions OIDC | 6, 8 |
| Clerk | 5, 8 (SSM + build args) |
| QA + Prod envs | 3, 5, 8 |
| Remove Vercel | 10 |
| af-south-1 | 3 (config) |

## Destroy order (document in infra/README.md)

```bash
cdk destroy RemitXQa RemitXProd
cdk destroy RemitXShared   # Aurora + EC2 — irreversible data loss
```

---

## Self-review

- No TBD placeholders in task steps.
- Aurora second database uses custom resource — called out explicitly (non-trivial CDK gap).
- EC2 worker code delivery via S3 + user-data is MVP; acceptable for plan.
- Vercel cron worker files removed in Task 10 to avoid dead code.

---

**Plan complete and saved to `docs/superpowers/plans/2026-08-17-aws-deployment.md`.**

Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — implement tasks in this session with checkpoints  

Which approach do you want?
