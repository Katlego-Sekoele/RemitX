# Relyo Infrastructure (Terraform)

Terraform layout for deploying Relyo to Azure. QA and Prod share the same modules under `modules/`; only environment-specific tfvars differ under `envs/`.

## Environment setup

Before running `terraform plan`, copy the example tfvars and fill in your values:

```bash
cp infra/envs/qa/terraform.tfvars.example infra/envs/qa/terraform.tfvars
# Edit terraform.tfvars with your alert emails and other settings
```

Never commit `terraform.tfvars` — it may contain secrets. Only `terraform.tfvars.example` is tracked in git.

## One-time backend bootstrap

Before `terraform init` can use remote state, create the state storage resources once (adjust the storage account name if `relyotfstate` is already taken globally):

Default region is `spaincentral`. **Azure for Students** subscriptions are restricted to a personal allowlist (~5 regions) — check Policy → *Allowed resource deployment regions* and use one of those if bootstrap fails.

```bash
az group create --name relyo-tfstate-rg --location spaincentral
az storage account create --name relyotfstate --resource-group relyo-tfstate-rg --location spaincentral --sku Standard_LRS
az storage container create --name tfstate --account-name relyotfstate
cd infra/envs/qa && terraform init && terraform plan
```

Expected: plan shows resource group, billing action group, and segment budgets to add.

## Billing alerts

Per-dollar Azure billing alerts fire on **Actual** spend at each whole dollar ($1, $2, … up to the configured cap). Azure allows only **5 notification thresholds per budget**, so the module creates **4 segment budgets** per scope (covering $1–5, $6–10, $11–15, $16–20 when the default cap is $20).

- **Resource group budgets** are always created for the environment's resource group.
- Set `enable_subscription_budget = true` in **prod only** for subscription-wide per-dollar alerts. Leave `false` in QA to avoid duplicate subscription-level resources.
- Increase `monthly_budget_cap` in **$5 increments** only (default `20` = alerts at $1–$20).
- Clerk and other non-Azure costs are **not** included in Azure budgets.

Set `budget_start_date` to the first day of the current month in ISO8601 (e.g. `2026-08-01T00:00:00Z`).

## Clerk (Terraform)

1. Create a Clerk application per environment in the [Clerk Dashboard](https://dashboard.clerk.com).
2. Export keys at apply time (never commit):

   ```bash
   export TF_VAR_clerk_api_key="sk_test_..."
   export TF_VAR_clerk_secret_key="sk_test_..."   # same value as api_key for Key Vault runtime
   export TF_VAR_clerk_publishable_key="pk_test_..."
   export TF_VAR_clerk_jwks_url="https://<instance>.clerk.accounts.dev/.well-known/jwks.json"
   ```

3. `terraform apply` creates `clerk_organization.relyo-<env>` in that Clerk application.

**Provider limitation:** bertie-technology/clerk v0.1 only manages organizations.
Clerk applications/instances are still created in the dashboard. Allowed origins
and redirect URLs are configured manually until a future provider version or auth plan.

### Production custom domains

Set `api_custom_domain` and `swa_custom_domain` in `infra/envs/prod/terraform.tfvars`
before applying prod. Terraform binds the domains to Container Apps (API) and Static
Web Apps (frontend) and outputs the verification records:

```bash
cd infra/envs/prod && terraform apply
terraform output api_custom_domain_dns_records
terraform output swa_custom_domain_dns_records
```

Create the TXT and CNAME records at your domain registrar (or Azure DNS). Azure
provisions managed TLS once DNS validates. For apex frontend domains (`example.com`),
SWA uses `dns-txt-token` validation; subdomains (`api.example.com`) use CNAME
delegation. Container Apps require both an `asuid.<hostname>` TXT record and a
CNAME to the default `*.azurecontainerapps.io` hostname.

After HTTPS is live, verify:

```bash
curl https://api.example.com/health
```

Leave `api_custom_domain` and `swa_custom_domain` empty in QA to use default Azure URLs.

### Clerk allowed origins (manual, prod)

After custom domains are live, open the **Production** Clerk application in the
[Clerk Dashboard](https://dashboard.clerk.com) and add these allowed origins
(and matching redirect URLs if prompted):

| Origin | Purpose |
|---|---|
| `https://<your-domain>` | Production frontend (SWA custom domain) |
| `https://api.<your-domain>` | Production API (Container Apps custom domain) |

Example for `example.com`: `https://example.com` and `https://api.example.com`.

Repeat for QA and Development apps with their respective URLs (`localhost:5173`,
QA SWA default hostname, etc.). This is not Terraform-managed until the Clerk
provider supports application settings.

## Azure DevOps pipelines

Terraform and deploy pipelines live under `azure-pipelines/`. Register each YAML file as a separate pipeline in [Azure DevOps](https://dev.azure.com) (Pipelines → New pipeline → GitHub → Existing Azure Pipelines YAML file).

| Pipeline file | Trigger | Variable group |
|---|---|---|
| `terraform-qa.yml` | PR/push to `qa`, `infra/**` | `relyo-qa-secrets` |
| `terraform-prod.yml` | PR/push to `main`, `infra/**` | `relyo-prod-secrets` |
| `deploy-api-qa.yml` | push to `qa`, `api/**` | `relyo-qa-secrets` |
| `deploy-api-prod.yml` | push to `main`, `api/**` | `relyo-prod-secrets` |
| `deploy-worker-qa.yml` | push to `qa`, `api/**` | `relyo-qa-secrets` |
| `deploy-worker-prod.yml` | push to `main`, `api/**` | `relyo-prod-secrets` |
| `deploy-frontend-qa.yml` | push to `qa`, `frontend/**` | `relyo-qa-secrets` |
| `deploy-frontend-prod.yml` | push to `main`, `frontend/**` | `relyo-prod-secrets` |

### One-time Azure service connection

1. In your Azure DevOps project: **Project settings → Service connections → New → Azure Resource Manager**.
2. Choose **Service principal (automatic)** (or **Manual** if your tenant blocks app registration).
3. Select the **Azure for Students** subscription and name the connection **`azure-relyo`** (must match `azureServiceConnection` in the pipeline YAML).

If automatic creation fails (common on university tenants), ask your IT admin to create a service principal and use a **Manual** connection with client ID + secret.

Grant the service connection's service principal:

- **Contributor** on `relyo-qa-rg`, `relyo-prod-rg` (or subscription scope until those exist)
- **Storage Blob Data Contributor** on `relyo-tfstate-rg`
- **Key Vault Secrets Officer** is wired via `azure_deployer_object_id` in Terraform — set `AZURE_DEPLOYER_OBJECT_ID` in the variable group to the service principal's object ID

### Variable groups

**Pipelines → Library → + Variable group** — create `relyo-qa-secrets` and `relyo-prod-secrets`.

Mark sensitive values with the lock icon.

| Variable | Used by |
|---|---|
| `TF_VAR_postgres_admin_password` | Terraform |
| `TF_VAR_clerk_api_key` | Terraform |
| `TF_VAR_clerk_secret_key` | Terraform |
| `TF_VAR_clerk_publishable_key` | Terraform |
| `TF_VAR_clerk_jwks_url` | Terraform |
| `TF_VAR_xrpl_encryption_key` | Terraform |
| `AZURE_DEPLOYER_OBJECT_ID` | Terraform — service principal object ID for Key Vault Secrets Officer |
| `GHCR_USER` | API/worker deploy — GitHub username for GHCR |
| `GHCR_PAT` | API/worker deploy — GitHub PAT with `write:packages` |
| `AZURE_STATIC_WEB_APPS_API_TOKEN` | Frontend deploy — from `terraform output` / SWA portal deployment token |
| `VITE_API_URL` | Frontend build |
| `VITE_CLERK_PUBLISHABLE_KEY` | Frontend build |

Non-sensitive Terraform inputs (`environment`, `alert_emails`, `budget_start_date`, custom domains, etc.) live in committed `non-secret.tfvars` per environment. Pipelines set `TF_VAR_ghcr_org` inline in the Terraform YAML.

### Pipeline behaviour

- **Pull request** to `qa` or `main` (with `infra/**` changes) → `terraform plan -var-file=non-secret.tfvars`
- **Push** to `qa` or `main` (merge) → `terraform apply -auto-approve -var-file=non-secret.tfvars`
- **Push** to `qa` or `main` with app changes → build container images, push to GHCR, `az containerapp update`
- **Push** with frontend changes → `npm run build`, deploy to Static Web Apps via deployment token

### Container image tags

Terraform provisions Container Apps with placeholder images tagged `:qa` or `:prod` (`ghcr.io/<owner>/<repo>/relyo-api:<env>`). Pipelines build, push `:qa`/`:prod` plus an immutable commit SHA tag, then update the running revision with the environment tag. Terraform ignores image changes after initial apply so deploys are not reverted.

For local `terraform apply`, pass `azure_deployer_object_id` in `non-secret.tfvars` or `TF_VAR_azure_deployer_object_id` with your user or SP object ID.

## Layout

- `modules/` — reusable Terraform modules
- `envs/qa/` — QA environment root module
- `envs/prod/` — Prod environment root module
