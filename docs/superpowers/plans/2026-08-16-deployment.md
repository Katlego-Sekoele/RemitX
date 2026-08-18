# RemitX Deployment Implementation Plan (superseded)

> **Superseded by [2026-08-17-vercel-deployment-design.md](../specs/2026-08-17-vercel-deployment-design.md) and [docs/DEPLOYMENT.md](../../DEPLOYMENT.md).** Do not execute this Azure/Terraform plan.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (historical) Stand up Local, QA, and Production deployment infrastructure (Azure + Clerk) with Terraform, GitHub Actions, Celery/Redis locally, and cloud Container Apps — matching the approved deployment spec. **Clerk application auth (Flask + React) is deferred**; this plan wires Clerk via Terraform and Key Vault only.

**Architecture:** Local uses Docker Compose (API, worker, Redis, Postgres). QA and Prod share identical Terraform modules with different `tfvars`. Azure hosts Static Web Apps (frontend), Container Apps (API, Celery worker, internal Redis), PostgreSQL Flexible Server B1MS, Key Vault, and Application Insights. Clerk is provisioned with the [`bertie-technology/clerk`](https://registry.terraform.io/providers/bertie-technology/clerk/latest/docs) Terraform provider (organizations + secret storage); runtime JWT integration comes in a later plan. GitHub Actions deploys via Azure OIDC.

**Tech Stack:** Terraform (`azurerm` + `bertie-technology/clerk` providers), Azure Container Apps, Azure Static Web Apps, Azure PostgreSQL Flexible Server, Azure Key Vault, GitHub Actions OIDC, Flask 3, Celery, Redis 7, gunicorn, GHCR for container images.

## Global Constraints

- XRPL **Testnet only**; no mainnet credentials in any environment.
- XRPL encryption key **must not** live in Postgres; use Key Vault in cloud, `.env` locally.
- **Max 2 providers:** Azure (infra) + Clerk (auth).
- **Python 3.9-compatible** runtime code (no `match`, no PEP 604 `X | Y` unions at runtime); Docker may use 3.11.
- **Single root `.env`** for local; update `.env.example` whenever adding env vars.
- **Never commit** `.env`, `terraform.tfstate`, or secrets.
- QA and Prod use **identical Terraform modules**; only `tfvars` differ.
- Pre-commit hooks (gitleaks, ruff, pytest, frontend lint) must pass before merging.
- Azure **billing alerts** at every whole-dollar threshold up to a configurable monthly cap (Terraform-managed).

---

## File Map (created or modified by this plan)

| Path | Responsibility |
|---|---|
| `infra/modules/resource-group/` | Azure resource group module |
| `infra/modules/budget-alerts/` | Per-dollar Azure Consumption budgets + email action group |
| `infra/modules/postgresql/` | Flexible Server + database |
| `infra/modules/key-vault/` | Key Vault + secret placeholders |
| `infra/modules/application-insights/` | Log Analytics + App Insights |
| `infra/modules/container-apps-env/` | Shared ACA environment |
| `infra/modules/container-app/` | Reusable ACA app (api, worker, redis) |
| `infra/modules/static-web-app/` | SWA resource |
| `infra/modules/clerk/` | Clerk provider wiring + `clerk_organization` |
| `infra/envs/qa/` | QA root module + backend |
| `infra/envs/prod/` | Prod root module + backend |
| `infra/README.md` | Bootstrap + apply instructions |
| `api/remitx_worker/celery_app.py` | Celery application factory |
| `api/remitx_worker/tasks.py` | Settlement task stub |
| `api/tests/test_celery_ping.py` | Celery wiring test |
| `.github/workflows/terraform-qa.yml` | Terraform plan/apply for QA |
| `.github/workflows/terraform-prod.yml` | Terraform plan/apply for Prod |
| `.github/workflows/deploy-api.yml` | Build/push API image, update ACA |
| `.github/workflows/deploy-worker.yml` | Build/push worker image |
| `.github/workflows/deploy-frontend.yml` | Build/deploy SWA |
| `docker-compose.dev.yml` | Add `worker` service |
| `.env.example` | Clerk + Celery env vars |
| `api/pyproject.toml` | celery, redis, gunicorn deps |
| `api/Dockerfile` | Production image with gunicorn |
| `api/Dockerfile.worker` | Worker image (celery entrypoint) |

---

### Task 1: Terraform bootstrap and resource group module

**Files:**
- Create: `infra/modules/resource-group/main.tf`
- Create: `infra/modules/resource-group/variables.tf`
- Create: `infra/modules/resource-group/outputs.tf`
- Create: `infra/envs/qa/providers.tf`
- Create: `infra/envs/qa/backend.tf`
- Create: `infra/envs/qa/variables.tf`
- Create: `infra/envs/qa/main.tf`
- Create: `infra/envs/qa/terraform.tfvars.example`
- Create: `infra/README.md`

**Interfaces:**
- Produces: `module.resource_group.name` (string), `module.resource_group.location` (string)

- [ ] **Step 1: Create resource group module**

`infra/modules/resource-group/main.tf`:

```hcl
resource "azurerm_resource_group" "this" {
  name     = var.name
  location = var.location
  tags     = var.tags
}
```

`infra/modules/resource-group/variables.tf`:

```hcl
variable "name" { type = string }
variable "location" { type = string }
variable "tags" { type = map(string) default = {} }
```

`infra/modules/resource-group/outputs.tf`:

```hcl
output "name" { value = azurerm_resource_group.this.name }
output "location" { value = azurerm_resource_group.this.location }
output "id" { value = azurerm_resource_group.this.id }
```

- [ ] **Step 2: Create QA backend and providers**

`infra/envs/qa/providers.tf`:

```hcl
terraform {
  required_version = ">= 1.5.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "azurerm" {
  features {}
}
```

`infra/envs/qa/backend.tf` (fill in after bootstrap — see README):

```hcl
terraform {
  backend "azurerm" {
    resource_group_name  = "remitx-tfstate-rg"
    storage_account_name = "remitxtfstate"
    container_name       = "tfstate"
    key                  = "qa.terraform.tfstate"
  }
}
```

`infra/envs/qa/main.tf`:

```hcl
module "resource_group" {
  source   = "../../modules/resource-group"
  name     = "remitx-${var.environment}-rg"
  location = var.location
  tags     = var.tags
}
```

`infra/envs/qa/variables.tf`:

```hcl
variable "environment" { type = string }
variable "location" { type = string default = "spaincentral" }
variable "tags" { type = map(string) default = {} }
```

`infra/envs/qa/terraform.tfvars.example`:

```hcl
environment = "qa"
location    = "spaincentral"
tags = {
  project     = "remitx"
  environment = "qa"
}
```

- [ ] **Step 3: Write infra README with bootstrap commands**

`infra/README.md` must document one-time creation of:
- Resource group `remitx-tfstate-rg`
- Storage account `remitxtfstate` (globally unique — adjust name if taken)
- Container `tfstate`

Bootstrap commands:

```bash
az group create --name remitx-tfstate-rg --location spaincentral
az storage account create --name remitxtfstate --resource-group remitx-tfstate-rg --sku Standard_LRS
az storage container create --name tfstate --account-name remitxtfstate
cd infra/envs/qa && terraform init && terraform plan
```

Expected: plan shows 1 resource group to add.

- [ ] **Step 4: Commit**

```bash
git add infra/
git commit -m "infra: add Terraform bootstrap and resource group module"
```

---

### Task 2: Azure billing alerts (per-dollar notifications)

Azure allows **5 notification thresholds per budget**. To alert at every whole dollar up to `$20`, this module creates **4 segment budgets** (covering $1–5, $6–10, $11–15, $16–20) plus one **subscription-level** budget with the same pattern for total account spend.

**Files:**
- Create: `infra/modules/budget-alerts/main.tf`
- Create: `infra/modules/budget-alerts/variables.tf`
- Create: `infra/modules/budget-alerts/outputs.tf`
- Create: `infra/modules/budget-alerts/locals.tf`
- Modify: `infra/envs/qa/main.tf`
- Modify: `infra/envs/qa/variables.tf`
- Modify: `infra/envs/qa/terraform.tfvars.example`
- Modify: `infra/envs/prod/` (same variables when prod skeleton exists)
- Modify: `infra/README.md`

**Interfaces:**
- Consumes: `var.resource_group_id`, `var.alert_emails` (list of strings)
- Consumes: `var.monthly_budget_cap` (number, default `20`)
- Produces: `module.budget_alerts.action_group_id` (string)

- [ ] **Step 1: Create budget segments local**

`infra/modules/budget-alerts/locals.tf`:

```hcl
locals {
  cap         = var.monthly_budget_cap
  segment_size = 5
  segment_count = local.cap / local.segment_size

  segments = {
    for i in range(1, local.segment_count + 1) :
    i => {
      amount  = i * local.segment_size
      dollars = range((i - 1) * local.segment_size + 1, i * local.segment_size + 1)
    }
  }
}
```

- [ ] **Step 2: Action group + segment budgets**

`infra/modules/budget-alerts/main.tf`:

```hcl
resource "azurerm_monitor_action_group" "billing" {
  name                = "${var.name_prefix}-billing"
  resource_group_name = var.resource_group_name
  short_name          = "remitxbill"

  dynamic "email_receiver" {
    for_each = toset(var.alert_emails)
    content {
      name          = replace(email_receiver.value, "@", "-at-")
      email_address = email_receiver.value
    }
  }
}

resource "azurerm_consumption_budget_resource_group" "segment" {
  for_each = local.segments

  name              = "${var.name_prefix}-budget-${each.value.amount}usd"
  resource_group_id = var.resource_group_id

  amount     = each.value.amount
  time_grain = "Monthly"

  time_period {
    start_date = var.budget_start_date
  }

  dynamic "notification" {
    for_each = each.value.dollars
    content {
      enabled        = true
      threshold      = (notification.value / each.value.amount) * 100
      operator       = "GreaterThanOrEqualTo"
      threshold_type = "Actual"
      contact_emails = var.alert_emails
      contact_groups = [azurerm_monitor_action_group.billing.id]
    }
  }
}

resource "azurerm_consumption_budget_subscription" "segment" {
  for_each = var.enable_subscription_budget ? local.segments : {}

  name            = "${var.name_prefix}-sub-budget-${each.value.amount}usd"
  subscription_id = var.subscription_id
  amount          = each.value.amount
  time_grain      = "Monthly"

  time_period {
    start_date = var.budget_start_date
  }

  dynamic "notification" {
    for_each = each.value.dollars
    content {
      enabled        = true
      threshold      = (notification.value / each.value.amount) * 100
      operator       = "GreaterThanOrEqualTo"
      threshold_type = "Actual"
      contact_emails = var.alert_emails
      contact_groups = [azurerm_monitor_action_group.billing.id]
    }
  }
}
```

`infra/modules/budget-alerts/variables.tf`:

```hcl
variable "name_prefix" { type = string }
variable "resource_group_name" { type = string }
variable "resource_group_id" { type = string }
variable "subscription_id" { type = string }
variable "alert_emails" { type = list(string) }
variable "monthly_budget_cap" {
  type    = number
  default = 20
  validation {
    condition     = var.monthly_budget_cap >= 5 && var.monthly_budget_cap % 5 == 0
    error_message = "monthly_budget_cap must be a positive multiple of 5 (Azure allows 5 thresholds per budget segment)."
  }
}
variable "budget_start_date" { type = string }
variable "enable_subscription_budget" {
  type        = bool
  default     = false
  description = "Enable subscription-wide segment budgets. Set true in prod only (once per subscription)."
}
```

Default `budget_start_date`: first day of current month in ISO8601, set in env `tfvars` (e.g. `2026-08-01T00:00:00Z`).

- [ ] **Step 3: Wire module in QA `main.tf`**

```hcl
module "budget_alerts" {
  source              = "../../modules/budget-alerts"
  name_prefix         = "remitx-${var.environment}"
  resource_group_name = module.resource_group.name
  resource_group_id   = module.resource_group.id
  subscription_id     = data.azurerm_subscription.current.id
  alert_emails        = var.alert_emails
  monthly_budget_cap  = var.monthly_budget_cap
  budget_start_date   = var.budget_start_date
}

data "azurerm_subscription" "current" {}
```

Add to `infra/envs/qa/variables.tf`:

```hcl
variable "alert_emails" {
  type        = list(string)
  description = "Email addresses for per-dollar billing alerts"
}

variable "monthly_budget_cap" {
  type    = number
  default = 20
}

variable "budget_start_date" {
  type        = string
  description = "ISO8601 start date for monthly budgets, e.g. 2026-08-01T00:00:00Z"
}
```

`infra/envs/qa/terraform.tfvars.example`:

```hcl
alert_emails       = ["team@example.com"]
monthly_budget_cap = 20
budget_start_date  = "2026-08-01T00:00:00Z"
```

- [ ] **Step 4: Document in `infra/README.md`**

Explain:
- Alerts fire on **Actual** spend at each whole dollar ($1, $2, … up to cap) via **4 segment budgets** per resource group (Azure allows only 5 thresholds per budget).
- Set `enable_subscription_budget = true` in **prod only** for subscription-wide per-dollar alerts; leave `false` in QA to avoid duplicate subscription resources.
- Increase `monthly_budget_cap` in **$5 increments** only (default `20` = alerts at $1–$20).
- Clerk and other non-Azure costs are **not** included in Azure budgets.

- [ ] **Step 5: Verify plan**

```bash
cd infra/envs/qa && terraform plan
```

Expected: 1 action group + 4 resource-group segment budgets (+ 4 subscription segment budgets if `enable_subscription_budget = true`).

- [ ] **Step 6: Commit**

```bash
git add infra/modules/budget-alerts infra/envs/qa infra/README.md
git commit -m "infra: add per-dollar Azure billing alert budgets"
```

---

### Task 3: PostgreSQL and Key Vault modules

**Files:**
- Create: `infra/modules/postgresql/main.tf`
- Create: `infra/modules/postgresql/variables.tf`
- Create: `infra/modules/postgresql/outputs.tf`
- Create: `infra/modules/key-vault/main.tf`
- Create: `infra/modules/key-vault/variables.tf`
- Create: `infra/modules/key-vault/outputs.tf`
- Modify: `infra/envs/qa/main.tf`
- Modify: `infra/envs/qa/variables.tf`
- Modify: `infra/envs/qa/terraform.tfvars.example`

**Interfaces:**
- Consumes: `module.resource_group.name`, `module.resource_group.location`
- Produces: `module.postgresql.connection_string` (sensitive string)
- Produces: `module.key_vault.id`, `module.key_vault.uri`

- [ ] **Step 1: PostgreSQL module (B1MS burstable)**

`infra/modules/postgresql/main.tf`:

```hcl
resource "azurerm_postgresql_flexible_server" "this" {
  name                   = var.server_name
  resource_group_name    = var.resource_group_name
  location               = var.location
  version                = "16"
  administrator_login    = var.admin_username
  administrator_password = var.admin_password
  storage_mb             = 32768
  sku_name               = "B_Standard_B1ms"
  zone                   = "1"
}

resource "azurerm_postgresql_flexible_server_database" "this" {
  name      = var.database_name
  server_id = azurerm_postgresql_flexible_server.this.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_services" {
  name             = "allow-azure-services"
  server_id        = azurerm_postgresql_flexible_server.this.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}
```

Output connection string as:

```hcl
output "connection_string" {
  value     = "postgresql+psycopg2://${var.admin_username}:${var.admin_password}@${azurerm_postgresql_flexible_server.this.fqdn}:5432/${var.database_name}?sslmode=require"
  sensitive = true
}
```

- [ ] **Step 2: Key Vault module**

`infra/modules/key-vault/main.tf`:

```hcl
data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "this" {
  name                       = var.name
  location                   = var.location
  resource_group_name        = var.resource_group_name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  soft_delete_retention_days = 7
  purge_protection_enabled   = false
  rbac_authorization_enabled = true
}

resource "azurerm_key_vault_secret" "database_url" {
  name         = "database-url"
  value        = var.database_url
  key_vault_id = azurerm_key_vault.this.id
}

resource "azurerm_key_vault_secret" "redis_url" {
  name         = "redis-url"
  value        = var.redis_url
  key_vault_id = azurerm_key_vault.this.id
}

resource "azurerm_key_vault_secret" "clerk_secret_key" {
  name         = "clerk-secret-key"
  value        = var.clerk_secret_key
  key_vault_id = azurerm_key_vault.this.id
}

resource "azurerm_key_vault_secret" "xrpl_encryption_key" {
  name         = "xrpl-encryption-key"
  value        = var.xrpl_encryption_key
  key_vault_id = azurerm_key_vault.this.id
}
```

- [ ] **Step 3: Wire modules in QA `main.tf`**

Add variables: `postgres_admin_password`, `database_name`, `clerk_secret_key`, `xrpl_encryption_key` (all sensitive, passed via `TF_VAR_*` at apply time — never in committed tfvars).

Pass placeholder `redis_url = "redis://placeholder:6379/0"` until Task 4 creates Redis.

- [ ] **Step 4: Verify plan**

```bash
cd infra/envs/qa
TF_VAR_postgres_admin_password='...' TF_VAR_clerk_secret_key='...' TF_VAR_xrpl_encryption_key='...' terraform plan
```

Expected: postgres server, database, firewall rule, key vault, secrets.

- [ ] **Step 5: Commit**

```bash
git add infra/modules/postgresql infra/modules/key-vault infra/envs/qa
git commit -m "infra: add PostgreSQL and Key Vault modules"
```

---

### Task 4: Application Insights and Container Apps environment

**Files:**
- Create: `infra/modules/application-insights/main.tf`
- Create: `infra/modules/application-insights/variables.tf`
- Create: `infra/modules/application-insights/outputs.tf`
- Create: `infra/modules/container-apps-env/main.tf`
- Create: `infra/modules/container-apps-env/variables.tf`
- Create: `infra/modules/container-apps-env/outputs.tf`
- Modify: `infra/envs/qa/main.tf`

**Interfaces:**
- Produces: `module.application_insights.connection_string` (sensitive)
- Produces: `module.container_apps_env.id`, `module.container_apps_env.default_domain`

- [ ] **Step 1: Application Insights module**

```hcl
resource "azurerm_log_analytics_workspace" "this" {
  name                = var.name
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_application_insights" "this" {
  name                = var.name
  location            = var.location
  resource_group_name = var.resource_group_name
  workspace_id        = azurerm_log_analytics_workspace.this.id
  application_type    = "web"
}
```

- [ ] **Step 2: Container Apps environment module**

```hcl
resource "azurerm_container_app_environment" "this" {
  name                       = var.name
  location                   = var.location
  resource_group_name        = var.resource_group_name
  log_analytics_workspace_id = var.log_analytics_workspace_id
}
```

- [ ] **Step 3: Wire into QA and run plan**

Expected: log analytics workspace, app insights, ACA environment.

- [ ] **Step 4: Commit**

```bash
git commit -m "infra: add Application Insights and Container Apps environment"
```

---

### Task 5: Container App module (Redis, API, Worker)

**Files:**
- Create: `infra/modules/container-app/main.tf`
- Create: `infra/modules/container-app/variables.tf`
- Create: `infra/modules/container-app/outputs.tf`
- Modify: `infra/envs/qa/main.tf`
- Modify: `api/Dockerfile`
- Create: `api/Dockerfile.worker`

**Interfaces:**
- Produces: `module.redis.internal_url` (string, e.g. `redis://redis:6379/0` — internal ACA DNS name)
- Produces: `module.api.fqdn` (string)
- Produces: `module.worker.name` (string)

- [ ] **Step 1: Reusable container-app module**

Key variables: `name`, `container_app_environment_id`, `image`, `command`, `args`, `ingress_external`, `min_replicas`, `max_replicas`, `env_vars` (map), `secrets` (map of Key Vault refs).

For **Redis** app in QA `main.tf`:

```hcl
module "redis" {
  source                       = "../../modules/container-app"
  name                         = "remitx-${var.environment}-redis"
  container_app_environment_id = module.container_apps_env.id
  image                        = "redis:7-alpine"
  ingress_external             = false
  min_replicas                 = 1
  max_replicas                 = 1
  cpu                          = 0.25
  memory                       = "0.5Gi"
}
```

Internal Redis URL for Celery: `redis://<redis-app-name>:6379/0` (ACA internal DNS uses app name within environment).

- [ ] **Step 2: Update API Dockerfile for production**

`api/Dockerfile` — add gunicorn CMD:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY pyproject.toml .
COPY remitx_api/ remitx_api/
COPY remitx_worker/ remitx_worker/
RUN pip install --upgrade pip && pip install -e .
EXPOSE 4200
CMD ["gunicorn", "--bind", "0.0.0.0:4200", "--workers", "2", "wsgi:app"]
```

- [ ] **Step 3: Worker Dockerfile**

`api/Dockerfile.worker`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY pyproject.toml .
COPY remitx_api/ remitx_api/
COPY remitx_worker/ remitx_worker/
RUN pip install --upgrade pip && pip install -e .
CMD ["celery", "-A", "remitx_worker.celery_app", "worker", "--loglevel=info"]
```

- [ ] **Step 4: Wire API and worker modules in QA**

API module: external ingress, `min_replicas = 0`, image `ghcr.io/<org>/remitx-api:qa`, secrets from Key Vault for `DATABASE_URL`, `REDIS_URL`, `CLERK_SECRET_KEY`, `XRPL_ENCRYPTION_KEY`.

Worker module: no ingress, `min_replicas = 1`, same secrets.

Update Key Vault `redis-url` secret with actual internal URL after Redis module output is known (use `azurerm_key_vault_secret` update or Terraform dependency).

- [ ] **Step 5: Commit**

```bash
git add infra/modules/container-app api/Dockerfile api/Dockerfile.worker infra/envs/qa
git commit -m "infra: add Container App module and production Dockerfiles"
```

---

### Task 6: Static Web App module and QA env completion

**Files:**
- Create: `infra/modules/static-web-app/main.tf`
- Create: `infra/modules/static-web-app/variables.tf`
- Create: `infra/modules/static-web-app/outputs.tf`
- Modify: `infra/envs/qa/main.tf`
- Modify: `infra/envs/qa/terraform.tfvars.example`

**Interfaces:**
- Produces: `module.static_web_app.default_hostname` (string)
- Produces: `module.static_web_app.api_key` (sensitive — for GitHub Actions deploy)

- [ ] **Step 1: SWA module**

```hcl
resource "azurerm_static_web_app" "this" {
  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location
  sku_tier            = "Free"
  sku_size            = "Free"
}
```

- [ ] **Step 2: Wire SWA in QA, output all hostnames**

Add outputs in `infra/envs/qa/outputs.tf`:

```hcl
output "api_url" { value = "https://${module.api.fqdn}" }
output "frontend_url" { value = "https://${module.static_web_app.default_hostname}" }
```

- [ ] **Step 3: Copy QA to Prod skeleton**

Copy `infra/envs/qa/` → `infra/envs/prod/`; change `environment = "prod"`, backend key `prod.terraform.tfstate`, `database_name = "remitx_prod"`, `api_min_replicas = 1`, optional `custom_domain` variables (empty in QA, set in prod tfvars).

- [ ] **Step 4: Commit**

```bash
git add infra/
git commit -m "infra: add Static Web App module and prod environment skeleton"
```

---

### Task 7: Local Celery worker and Docker Compose

**Files:**
- Create: `api/remitx_worker/__init__.py`
- Create: `api/remitx_worker/celery_app.py`
- Create: `api/remitx_worker/tasks.py`
- Create: `api/tests/test_celery_ping.py`
- Modify: `api/pyproject.toml`
- Modify: `docker-compose.dev.yml`
- Modify: `.env.example`

**Interfaces:**
- Produces: `remitx_worker.celery_app.celery` (Celery instance)
- Produces: `remitx_worker.tasks.ping` (Celery task name: `remitx_worker.tasks.ping`)
- Produces: `remitx_worker.tasks.settle_remittance` (Celery task name: `remitx_worker.tasks.settle_remittance`, arg: `remittance_id: str`)

- [ ] **Step 1: Add dependencies to `api/pyproject.toml`**

```toml
dependencies = [
    "flask>=3.1.0",
    "flask-sqlalchemy>=3.1.0",
    "psycopg2-binary>=2.9.0",
    "python-dotenv>=1.0.0",
    "celery>=5.4.0",
    "redis>=5.0.0",
]
```

- [ ] **Step 2: Write failing Celery test**

`api/tests/test_celery_ping.py`:

```python
from remitx_worker.celery_app import celery
from remitx_worker.tasks import ping


def test_celery_ping_task_registered():
    assert "remitx_worker.tasks.ping" in celery.tasks


def test_ping_returns_pong():
    result = ping.apply(args=[])
    assert result.get(timeout=10) == "pong"
```

Note: test requires Redis running; mark with `@pytest.mark.integration` or skip if `REDIS_URL` unreachable in CI unit runs. For local dev:

```python
import os
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_REDIS_TESTS", "1") == "1",
    reason="Redis not available",
)
```

Default `SKIP_REDIS_TESTS=1` in CI pytest; run with `SKIP_REDIS_TESTS=0` when compose is up.

- [ ] **Step 3: Implement Celery app**

`api/remitx_worker/celery_app.py`:

```python
import os

from celery import Celery

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery = Celery("remitx_worker", broker=redis_url, backend=redis_url)
celery.conf.task_default_queue = "settlement"
celery.conf.task_acks_late = True
celery.autodiscover_tasks(["remitx_worker"])
```

`api/remitx_worker/tasks.py`:

```python
from remitx_worker.celery_app import celery


@celery.task(name="remitx_worker.tasks.ping")
def ping():
    return "pong"


@celery.task(name="remitx_worker.tasks.settle_remittance", bind=True, max_retries=3)
def settle_remittance(self, remittance_id: str):
    # Stub — XRPL settlement implemented in a later feature plan
    return {"remittance_id": remittance_id, "status": "stub"}
```

- [ ] **Step 4: Add worker service to compose**

`docker-compose.dev.yml`:

```yaml
  worker:
    build:
      context: ./api
      dockerfile: Dockerfile.worker
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      REDIS_URL: redis://redis:6379/0
    volumes:
      - ./api:/app
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
```

- [ ] **Step 5: Update `.env.example`**

Add commented placeholders:

```bash
# --- Clerk (auth) ---
CLERK_SECRET_KEY=
CLERK_JWKS_URL=
VITE_CLERK_PUBLISHABLE_KEY=

# --- Celery / worker ---
# REDIS_URL already defined above
SKIP_REDIS_TESTS=1
```

- [ ] **Step 6: Verify locally**

```bash
docker compose -f docker-compose.dev.yml up --build -d
cd api && SKIP_REDIS_TESTS=0 pytest tests/test_celery_ping.py -v
```

Expected: PASS (with Redis up).

- [ ] **Step 7: Commit**

```bash
git add api/remitx_worker api/pyproject.toml api/tests/test_celery_ping.py docker-compose.dev.yml .env.example
git commit -m "feat: add Celery worker package and local compose service"
```

---

### Task 8: Clerk Terraform infrastructure (no app auth yet)

**Provider:** [`bertie-technology/clerk`](https://registry.terraform.io/providers/bertie-technology/clerk/latest/docs) (v0.1.x). Authenticates with `CLERK_API_KEY` (the Clerk **Secret Key** from that environment’s Clerk application). Currently exposes one resource: [`clerk_organization`](https://registry.terraform.io/providers/bertie-technology/clerk/latest/docs/resources/organization).

**Scope:** Wire the provider, create a platform organization per environment, and store Clerk keys in Key Vault. **Do not** implement Flask JWT middleware or React `ClerkProvider` in this plan.

**Manual prerequisite (per environment):** In the [Clerk Dashboard](https://dashboard.clerk.com), create a separate application for **QA** and **Production**. Copy each app’s Secret Key, Publishable Key, and JWKS URL. Local dev uses a third **Development** application (keys in `.env` only).

**Files:**
- Create: `infra/modules/clerk/main.tf`
- Create: `infra/modules/clerk/variables.tf`
- Create: `infra/modules/clerk/outputs.tf`
- Modify: `infra/envs/qa/providers.tf` (add `clerk` provider)
- Modify: `infra/envs/prod/providers.tf` (copy from qa)
- Modify: `infra/envs/qa/main.tf`
- Modify: `infra/envs/qa/variables.tf`
- Modify: `infra/envs/qa/outputs.tf`
- Modify: `infra/modules/key-vault/main.tf` (add publishable key + JWKS secrets)
- Modify: `infra/modules/key-vault/variables.tf`
- Modify: `infra/README.md` (Clerk provider section)
- Modify: `.env.example` (commented Clerk placeholders for future auth work)

**Interfaces:**
- Consumes: `var.clerk_api_key` (sensitive — QA or Prod Clerk Secret Key)
- Consumes: `var.clerk_publishable_key`, `var.clerk_jwks_url` (for Key Vault)
- Produces: `module.clerk.organization_id` (string)
- Produces: Key Vault secrets: `clerk-secret-key`, `clerk-publishable-key`, `clerk-jwks-url`

- [ ] **Step 1: Add Clerk provider to environment `providers.tf`**

`infra/envs/qa/providers.tf`:

```hcl
terraform {
  required_version = ">= 1.5.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    clerk = {
      source  = "bertie-technology/clerk"
      version = "~> 0.1.0"
    }
  }
}

provider "azurerm" {
  features {}
}

provider "clerk" {
  api_key = var.clerk_api_key
}
```

Add to `infra/envs/qa/variables.tf`:

```hcl
variable "clerk_api_key" {
  type      = string
  sensitive = true
  description = "Clerk Secret Key (sk_test_... or sk_live_...) for this environment's Clerk application"
}

variable "clerk_publishable_key" {
  type        = string
  description = "Clerk Publishable Key (pk_...) for frontend — stored in Key Vault for later use"
}

variable "clerk_jwks_url" {
  type        = string
  description = "Clerk JWKS URL for JWT verification — stored in Key Vault for later use"
}
```

- [ ] **Step 2: Create Clerk module**

`infra/modules/clerk/main.tf`:

```hcl
resource "clerk_organization" "platform" {
  name = var.organization_name
  slug = var.organization_slug

  public_metadata = jsonencode({
    project     = "remitx"
    environment = var.environment
  })
}
```

`infra/modules/clerk/variables.tf`:

```hcl
variable "organization_name" { type = string }
variable "organization_slug" { type = string }
variable "environment" { type = string }
```

`infra/modules/clerk/outputs.tf`:

```hcl
output "organization_id" {
  value = clerk_organization.platform.id
}

output "organization_slug" {
  value = clerk_organization.platform.slug
}
```

- [ ] **Step 3: Extend Key Vault with Clerk secrets**

Add to `infra/modules/key-vault/main.tf`:

```hcl
resource "azurerm_key_vault_secret" "clerk_publishable_key" {
  name         = "clerk-publishable-key"
  value        = var.clerk_publishable_key
  key_vault_id = azurerm_key_vault.this.id
}

resource "azurerm_key_vault_secret" "clerk_jwks_url" {
  name         = "clerk-jwks-url"
  value        = var.clerk_jwks_url
  key_vault_id = azurerm_key_vault.this.id
}
```

Pass `clerk_secret_key`, `clerk_publishable_key`, and `clerk_jwks_url` into the Key Vault module from root `main.tf`.

- [ ] **Step 4: Wire Clerk module in QA `main.tf`**

```hcl
module "clerk" {
  source            = "../../modules/clerk"
  organization_name = "RemitX ${title(var.environment)}"
  organization_slug   = "remitx-${var.environment}"
  environment       = var.environment
}
```

Add outputs in `infra/envs/qa/outputs.tf`:

```hcl
output "clerk_organization_id" {
  value = module.clerk.organization_id
}
```

- [ ] **Step 5: Document Clerk setup in `infra/README.md`**

Include:

```markdown
## Clerk (Terraform)

1. Create a Clerk application per environment in the Clerk Dashboard.
2. Export keys at apply time (never commit):

   export TF_VAR_clerk_api_key="sk_test_..."
   export TF_VAR_clerk_secret_key="sk_test_..."   # same value as api_key for Key Vault runtime
   export TF_VAR_clerk_publishable_key="pk_test_..."
   export TF_VAR_clerk_jwks_url="https://<instance>.clerk.accounts.dev/.well-known/jwks.json"

3. `terraform apply` creates `clerk_organization.remitx-<env>` in that Clerk application.

**Provider limitation:** bertie-technology/clerk v0.1 only manages organizations.
Clerk applications/instances are still created in the dashboard. Allowed origins
and redirect URLs are configured manually until a future provider version or auth plan.
```

- [ ] **Step 6: Update `.env.example` (placeholders only — no implementation)**

```bash
# --- Clerk (auth — infrastructure keys; app integration deferred) ---
# Create a Clerk Development application at https://dashboard.clerk.com
CLERK_SECRET_KEY=
CLERK_JWKS_URL=
VITE_CLERK_PUBLISHABLE_KEY=
```

- [ ] **Step 7: Verify Terraform plan**

```bash
cd infra/envs/qa
TF_VAR_clerk_api_key='sk_test_...' \
TF_VAR_clerk_secret_key='sk_test_...' \
TF_VAR_clerk_publishable_key='pk_test_...' \
TF_VAR_clerk_jwks_url='https://....clerk.accounts.dev/.well-known/jwks.json' \
TF_VAR_postgres_admin_password='...' \
TF_VAR_xrpl_encryption_key='...' \
terraform init && terraform plan
```

Expected: plan includes `clerk_organization.platform` plus Key Vault Clerk secrets.

- [ ] **Step 8: Commit**

```bash
git add infra/modules/clerk infra/envs infra/README.md .env.example
git commit -m "infra: add Clerk Terraform provider and Key Vault secret wiring"
```

---

### Task 9: GitHub Actions — Azure OIDC and Terraform QA

**Files:**
- Create: `.github/workflows/terraform-qa.yml`
- Create: `.github/workflows/terraform-prod.yml`
- Modify: `infra/README.md` (document OIDC app registration)

**Interfaces:**
- Consumes: GitHub secrets `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`
- Consumes: GitHub environment secrets for QA: `TF_VAR_postgres_admin_password`, `TF_VAR_clerk_api_key`, `TF_VAR_clerk_secret_key`, `TF_VAR_clerk_publishable_key`, `TF_VAR_clerk_jwks_url`, `TF_VAR_xrpl_encryption_key`

- [ ] **Step 1: Register Azure AD app for OIDC**

Document in `infra/README.md`:

```bash
# Create app registration + federated credential for GitHub repo
# Assign Contributor on remitx-qa-rg / remitx-prod-rg
```

Federated credential subject: `repo:<org>/RemitX:environment:qa`

- [ ] **Step 2: Terraform QA workflow**

`.github/workflows/terraform-qa.yml`:

```yaml
name: Terraform QA

on:
  pull_request:
    branches: [qa]
    paths: ["infra/**"]
  push:
    branches: [qa]
    paths: ["infra/**"]

permissions:
  id-token: write
  contents: read

jobs:
  terraform:
    runs-on: ubuntu-latest
    environment: qa
    defaults:
      run:
        working-directory: infra/envs/qa
    steps:
      - uses: actions/checkout@v4
      - uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      - uses: hashicorp/setup-terraform@v3
      - run: terraform init
      - run: terraform plan
        if: github.event_name == 'pull_request'
      - run: terraform apply -auto-approve
        if: github.event_name == 'push'
        env:
          TF_VAR_postgres_admin_password: ${{ secrets.TF_VAR_postgres_admin_password }}
          TF_VAR_clerk_api_key: ${{ secrets.TF_VAR_clerk_api_key }}
          TF_VAR_clerk_secret_key: ${{ secrets.TF_VAR_clerk_secret_key }}
          TF_VAR_clerk_publishable_key: ${{ secrets.TF_VAR_clerk_publishable_key }}
          TF_VAR_clerk_jwks_url: ${{ secrets.TF_VAR_clerk_jwks_url }}
          TF_VAR_xrpl_encryption_key: ${{ secrets.TF_VAR_xrpl_encryption_key }}
```

Copy for prod with `branches: [main]`, `environment: prod`, `working-directory: infra/envs/prod`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows infra/README.md
git commit -m "ci: add Terraform QA and Prod workflows with Azure OIDC"
```

---

### Task 10: GitHub Actions — deploy API, worker, and frontend

**Files:**
- Create: `.github/workflows/deploy-api.yml`
- Create: `.github/workflows/deploy-worker.yml`
- Create: `.github/workflows/deploy-frontend.yml`

- [ ] **Step 1: Deploy API workflow**

Build and push to GHCR on push to `qa`/`main` when `api/**` changes:

```yaml
name: Deploy API

on:
  push:
    branches: [qa, main]
    paths: ["api/**"]

permissions:
  id-token: write
  contents: read
  packages: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: ${{ github.ref_name == 'main' && 'prod' || 'qa' }}
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          context: ./api
          push: true
          tags: ghcr.io/${{ github.repository }}/remitx-api:${{ github.sha }}
      - uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      - run: |
          az containerapp update \
            --name remitx-${{ github.ref_name == 'main' && 'prod' || 'qa' }}-api \
            --resource-group remitx-${{ github.ref_name == 'main' && 'prod' || 'qa' }}-rg \
            --image ghcr.io/${{ github.repository }}/remitx-api:${{ github.sha }}
```

- [ ] **Step 2: Deploy worker workflow**

Same pattern using `Dockerfile.worker` and `remitx-worker` image name.

- [ ] **Step 3: Deploy frontend workflow**

Use `Azure/static-web-apps-deploy@v1` with `app_location: frontend`, `output_location: build/client` (verify React Router 7 build output path with `npm run build` locally first).

Pass `VITE_API_URL` and `VITE_CLERK_PUBLISHABLE_KEY` as build env from GitHub environment secrets.

- [ ] **Step 4: Commit and dry-run**

```bash
git add .github/workflows
git commit -m "ci: add API, worker, and frontend deploy workflows"
```

- [ ] **Step 5: First QA deploy**

1. Create `qa` branch, push, merge Terraform workflow → provisions Azure QA
2. Push API change → deploy-api workflow updates Container App
3. Verify `https://<api-fqdn>/health` returns OK

---

### Task 11: Production custom domain

**Files:**
- Create: `infra/modules/dns/main.tf` (optional — or document manual registrar CNAMEs)
- Modify: `infra/envs/prod/variables.tf`
- Modify: `infra/envs/prod/terraform.tfvars.example`
- Modify: `infra/modules/container-app/main.tf` (custom domain binding)
- Modify: `infra/modules/static-web-app/main.tf` (custom domain binding)

- [ ] **Step 1: Add domain variables to prod**

```hcl
variable "api_custom_domain" { type = string default = "" }
variable "frontend_custom_domain" { type = string default = "" }
```

- [ ] **Step 2: Bind custom domains in modules**

Use `azurerm_container_app_custom_domain` and SWA custom domain resource; output TXT/CNAME verification records in Terraform outputs.

- [ ] **Step 3: Configure Clerk allowed origins (manual)**

In each Clerk application’s dashboard, add allowed origins for prod: `https://<domain>`, `https://api.<domain>`. (Not Terraform-managed until provider supports it.)

- [ ] **Step 4: Apply prod Terraform and verify HTTPS**

```bash
cd infra/envs/prod && terraform apply
curl https://api.<domain>/health
```

- [ ] **Step 5: Commit**

```bash
git commit -m "infra: add production custom domain support"
```

---

## Spec Coverage Self-Review

| Spec requirement | Task |
|---|---|
| Local Docker (API, worker, Redis, Postgres) | Task 7 |
| Azure PostgreSQL B1MS | Task 3 |
| Container Apps (API, worker, internal Redis) | Tasks 4–5 |
| Static Web Apps | Task 6 |
| Key Vault secrets | Task 3 |
| Application Insights | Task 4 |
| Per-dollar billing alerts | Task 2 |
| Clerk Terraform (`clerk_organization` + KV secrets) | Task 8 |
| Terraform modules + QA/Prod envs | Tasks 1–6, 11 |
| GitHub Actions OIDC | Task 9 |
| Deploy workflows | Task 10 |
| Custom domain (prod) | Task 11 |
| Celery settlement stub + idempotency hook | Task 7 (`settle_remittance` stub) |
| `.env.example` updates | Tasks 7, 8 |
| Cost constraints (free tiers, no Azure Redis Cache) | Tasks 3, 5 (internal Redis container) |

**Deferred to follow-up plans:**

- Flask Clerk JWT middleware + `/me` endpoint
- React `ClerkProvider` + sign-in UI
- XRPL settlement logic, encrypted wallet keys in DB, remittance domain models
- Perf load tests, Postgres `FOR UPDATE` idempotency in worker

---

## Suggested Branch Strategy

| Branch | Deploys to |
|---|---|
| feature branches | local only |
| `qa` | QA Azure environment |
| `main` | Production Azure environment |

Create GitHub Environments `qa` and `prod` with required reviewers on `prod`.

---

## Manual Prerequisites (human steps before Task 9)

1. Azure student subscription active.
2. Team email addresses for billing alerts (`alert_emails` in tfvars) — alerts at **every whole dollar** up to `monthly_budget_cap` (default $20).
3. Clerk account with **Development**, **QA**, and **Production** applications created in the [Clerk Dashboard](https://dashboard.clerk.com). Copy Secret Key, Publishable Key, and JWKS URL per app.
4. Generate `XRPL_ENCRYPTION_KEY` locally: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
5. Choose GHCR image visibility (public repo → public packages OK).
6. Decide domain registrar DNS access for Task 11.
7. GitHub Environment secrets for `qa` / `prod`: all `TF_VAR_*` values from Task 8 (including `TF_VAR_clerk_api_key`).
