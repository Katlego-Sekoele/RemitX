# RemitX Deployment Design — AWS Stack

**Date:** 2026-08-17  
**Status:** Superseded by [2026-08-18-azure-neon-deployment-design.md](./2026-08-18-azure-neon-deployment-design.md)

## Summary

RemitX deploys to **AWS** with **AWS CDK (Python)** for IaC, **GitHub Actions (OIDC)** for CI/CD, and **Docker Compose** unchanged as the local dev story (Postgres + RabbitMQ + Celery). Cloud uses **QA** (`qa` branch) and **Production** (`main` branch) with **cost-sharing** on one Aurora cluster and one EC2 RabbitMQ host.

## Target stack

| Component | Technology |
|-----------|------------|
| Frontend | **S3** + **CloudFront** (React Router **SPA**) |
| API | **Lambda** + **Function URL** |
| API framework | **Flask** (Mangum adapter) |
| Database | **Aurora PostgreSQL Serverless v2** — **one cluster**, databases `remitx_qa` and `remitx_prod` |
| Message broker | **RabbitMQ** on **EC2** (shared) |
| Async processing | **Celery workers** on same EC2 (one worker process per env) |
| Auth | **Clerk** (JWT validation in API; publishable key in SPA build) |
| Secrets | **SSM Parameter Store** — Standard **SecureString** |
| Logging | **CloudWatch Logs** |
| IaC | **AWS CDK** (Python) under `infra/cdk/` |
| CI/CD | **GitHub Actions** — tests on PR; `cdk deploy` on push to `qa` / `main` |
| Local | Docker Compose — PostgreSQL, RabbitMQ, Celery worker, API, frontend |
| Blockchain | XRPL **Testnet** only (unchanged from project brief) |

## Architecture

```
                         ┌──────────────────────────────────────────┐
                         │  Shared EC2 (e.g. t4g.small)             │
                         │  RabbitMQ                                │
                         │    vhost remitx-qa  │  vhost remitx-prod   │
                         │  celery worker qa  │  celery worker prod │
                         └────────────▲─────────────────────────────┘
                                      │ AMQP (5672, private VPC)
┌─────────┐   HTTPS    ┌──────────────┴──────────────┐
│ Browser │ ─────────► │ CloudFront → S3 (SPA)       │  ×2 (qa / prod distributions)
└────┬────┘            └─────────────────────────────┘
     │ Clerk JWT
     ▼
┌─────────────┐  publish   ┌─────────────┐
│ Lambda API  │ ─────────► │  RabbitMQ   │
│ (Flask)     │            └─────────────┘
└──────┬──────┘
       │ SQL
       ▼
┌──────────────────────────────────────┐
│ Aurora PostgreSQL Serverless v2      │
│  cluster: remitx                        │
│    ├── database remitx_qa   (QA)       │
│    └── database remitx_prod (Prod)     │
└──────────────────────────────────────┘
```

Lambda runs in the **VPC** (private subnets) to reach Aurora and the EC2 broker. Function URL is public HTTPS; **authorization is Clerk at the Flask layer**, not IAM on the URL.

## Environments

| | Local | QA | Production |
|--|-------|-----|------------|
| Git branch | any | `qa` | `main` |
| Frontend | Vite `:5173` | CloudFront + S3 | CloudFront + S3 |
| API | Flask `:4200` | Lambda + Function URL | Lambda + Function URL |
| Postgres | Docker | Aurora DB `remitx_qa` | Aurora DB `remitx_prod` |
| RabbitMQ | Docker | vhost `remitx-qa` | vhost `remitx-prod` |
| Celery | Compose worker | EC2 worker (qa) | EC2 worker (prod) |
| Clerk app | Development | QA | Production |

### Shared vs per-env resources

| Resource | Shared | Per-env |
|----------|--------|---------|
| Aurora **cluster** | ✓ one | two **databases** on instance |
| EC2 RabbitMQ host | ✓ one | two **vhosts** + two **Celery workers** |
| Lambda, S3, CloudFront, SSM prefix | | ✓ each |

**Blast radius:** QA traffic or a bad Celery deploy on shared EC2 can affect broker availability for prod. Acceptable for course prototype; vhosts isolate queues.

### Git workflow

```
feature/* ──PR──► qa ──PR──► main
                  │           │
            deploy QaStack   deploy ProdStack
            (+ SharedStack as needed)
```

## CDK structure (recommended)

```
infra/cdk/
  app.py
  stacks/
    shared_stack.py   # VPC, EC2, RabbitMQ, shared SGs, SSM for broker host
    env_stack.py      # Aurora (cluster created once; DB per env), Lambda, S3, CF, SSM, CW
    github_oidc_stack.py  # IAM role for GitHub Actions (optional separate stack)
```

**Deploy order**

1. `SharedStack` — once (or when broker changes)
2. `QaStack` / `ProdStack` — independently on branch push

First env deploy creates the Aurora cluster; second env deploy adds the other database to the same cluster (CDK/custom resource or single cluster resource owned by SharedStack with both DBs — implementation detail in plan).

**Preferred ownership:** Aurora **cluster** in `SharedStack`; `remitx_qa` and `remitx_prod` databases created there; env stacks receive cluster endpoint + database name via SSM/exports.

## Component details

### Frontend (SPA)

- Set React Router **`ssr: false`**; build static assets to `frontend/build/client` (or current RR SPA output path).
- CDK: S3 bucket (private) + CloudFront OAC + bucket deployment on CI/CD.
- Build-time: `VITE_API_URL` (Function URL), `VITE_CLERK_PUBLISHABLE_KEY`.

### API (Lambda + Flask)

- **Mangum** wraps `create_app()` from `remitx_api`.
- **Lambda container image** (recommended) for Flask + psycopg2 + Celery client dependencies.
- **Function URL** with CORS configured for CloudFront origin(s).
- Environment from SSM: `DATABASE_URL`, `CELERY_BROKER_URL`, Clerk keys, `XRPL_ENCRYPTION_KEY`.
- **Celery:** API is producer only (`apply_async` / `delay`); broker URL points at shared EC2 RabbitMQ with env-specific vhost.

### Aurora

- **Engine:** Aurora PostgreSQL Serverless v2.
- **Region default:** `af-south-1` (Cape Town) if account supports it.
- **One cluster** (e.g. `remitx`), minimum ACU tuned for cost (QA can use low min; prod slightly higher for demo reliability).
- **Databases:** `remitx_qa`, `remitx_prod` — separate connection strings, no shared `search_path`.
- Credentials: master secret in Secrets Manager or SSM; app URLs in SSM SecureString per env.
- Schema: migrations TBD; bootstrap via controlled `create_all` or Alembic in implementation plan.

### RabbitMQ + Celery (EC2)

- **One EC2** (e.g. **t4g.small**): RabbitMQ via Docker (match Compose) or native install.
- **Two vhosts:** `remitx-qa`, `remitx-prod`; separate users/passwords in SSM.
- **Two systemd services:** `celery -A remitx_worker.celery_app worker` with env-specific unit files reading SSM.
- **Security:** broker port 5672 only from Lambda SG and EC2 SG; management UI not public.
- **Admin access:** SSM Session Manager (no SSH keys in repo).

**Local parity:** Replace Redis with RabbitMQ in `docker-compose.dev.yml`; set `CELERY_BROKER_URL=amqp://guest:guest@rabbitmq:5672//` (or dedicated vhost).

### Secrets (SSM Parameter Store)

Prefix convention:

| Path | Contents |
|------|----------|
| `/remitx/shared/` | Broker hostname, optional shared read-only params |
| `/remitx/qa/` | `database-url`, `celery-broker-url`, `clerk-secret-key`, `clerk-jwks-url`, `xrpl-encryption-key` |
| `/remitx/prod/` | Same keys, prod values |

Clerk **publishable** keys: SSM String or CI env (not SecureString). Populate manually or via CDK placeholders on first deploy; never commit values.

### Logging

- Lambda: `/aws/lambda/remitx-api-qa`, `/aws/lambda/remitx-api-prod` — retention 7–14 days.
- EC2 Celery: CloudWatch agent or journald ship to `/remitx/qa/celery`, `/remitx/prod/celery`.

### Duplicate-message protection (brief)

- Celery `apply_async(..., task_id=f"settle-{remittance_id}")` where applicable.
- Consumer settlement must be **idempotent** (DB status gate / unique constraint).
- Manual ack after successful processing (Celery default with acks_late on settlement task when implemented).

## CI/CD

| Workflow | Trigger | Action |
|----------|---------|--------|
| `ci.yml` | PR, push | `pytest`, frontend lint/typecheck |
| `deploy-aws.yml` | push `qa` | Build SPA → S3; build/push Lambda image; `cdk deploy QaStack` |
| | push `main` | Same for prod; `SharedStack` when infra changes |

- **GitHub OIDC** → IAM role (no static AWS keys).
- **Destroy:** `cdk destroy QaStack` / `ProdStack`; `SharedStack` last (drops Aurora cluster + EC2 — **data loss**).

## Cost notes (student prototype)

| Shared | Approx. saving |
|--------|----------------|
| One EC2 vs two | ~$6–15/mo |
| One Aurora cluster, two DBs vs two clusters | **Largest saving** — often $30+/mo |

Still pay for: CloudFront, Lambda invocations, Aurora minimum ACU, EC2 24/7. Use AWS credits; destroy QA stack when idle.

## Out of scope (this spec)

- Vercel / Neon / Upstash deployment paths (superseded)
- Amazon MQ (managed RabbitMQ)
- Lambda Event Source Mapping for queues
- Cognito (using Clerk)
- XRPL mainnet
- Multi-region

## Local vs cloud queue

Both use **Celery + RabbitMQ**. Local Compose runs broker + worker; cloud runs broker + workers on EC2; Lambda is **producer only**.

## Migration from current repo (implementation plan)

When approved for build:

1. Add `infra/cdk/` and supersede `vercel/`, `scripts/cloud/`, `worker/` Vercel artifacts.
2. Switch Compose from Redis to RabbitMQ; point `celery_app` at AMQP.
3. Frontend SPA mode + S3 deploy path.
4. Lambda handler + VPC wiring.
5. GitHub Actions AWS deploy.
6. Update `CLAUDE.md`, `docs/DEPLOYMENT.md`, `.env.example`.

## Open implementation choices (non-blocking)

- Lambda **zip** vs **container image** (spec recommends container).
- Aurora cluster resource in **SharedStack** vs **first env stack** (spec recommends SharedStack).
- Custom domain on CloudFront (optional, prod only).
