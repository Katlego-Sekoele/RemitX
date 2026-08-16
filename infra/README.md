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

```bash
az group create --name relyo-tfstate-rg --location southafricanorth
az storage account create --name relyotfstate --resource-group relyo-tfstate-rg --sku Standard_LRS
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

## GitHub Actions — Azure OIDC

Terraform QA and Prod workflows (`.github/workflows/terraform-qa.yml`, `terraform-prod.yml`) authenticate to Azure via **OIDC federation** — no long-lived `AZURE_CLIENT_SECRET` in GitHub.

### One-time Azure AD app registration

Replace `<org>` with your GitHub org or username (e.g. `Katlego-Sekoele`).

```bash
# Create app registration (note appId in output — this is AZURE_CLIENT_ID)
az ad app create --display-name "relyo-github-actions"

APP_ID="<app-id-from-above>"
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)

# Federated credential for GitHub environment: qa
az ad app federated-credential create \
  --id "$APP_ID" \
  --parameters '{
    "name": "relyo-github-qa",
    "issuer": "https://token.actions.githubusercontent.com",
    "subject": "repo:<org>/Relyo:environment:qa",
    "audiences": ["api://AzureADTokenExchange"]
  }'

# Federated credential for GitHub environment: prod
az ad app federated-credential create \
  --id "$APP_ID" \
  --parameters '{
    "name": "relyo-github-prod",
    "issuer": "https://token.actions.githubusercontent.com",
    "subject": "repo:<org>/Relyo:environment:prod",
    "audiences": ["api://AzureADTokenExchange"]
  }'

# Service principal + Contributor on environment resource groups
az ad sp create --id "$APP_ID"
SP_OBJECT_ID=$(az ad sp show --id "$APP_ID" --query id -o tsv)

az role assignment create --assignee-object-id "$SP_OBJECT_ID" --assignee-principal-type ServicePrincipal \
  --role Contributor --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/relyo-qa-rg"
az role assignment create --assignee-object-id "$SP_OBJECT_ID" --assignee-principal-type ServicePrincipal \
  --role Contributor --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/relyo-prod-rg"

# Remote state storage (bootstrap section above)
az role assignment create --assignee-object-id "$SP_OBJECT_ID" --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/relyo-tfstate-rg"
```

First `terraform apply` creates `relyo-qa-rg` / `relyo-prod-rg` if they do not exist yet — until then, assign **Contributor** at subscription scope (or pre-create the resource groups), then narrow to RG scope above.

Key Vault uses RBAC. Terraform grants the deployer **Key Vault Secrets Officer** via `azure_deployer_object_id` (wired from `AZURE_DEPLOYER_OBJECT_ID` in GitHub Actions). Set that variable to the service principal object ID (`$SP_OBJECT_ID` above):

```bash
# GitHub → Settings → Environments → qa / prod → Variables
AZURE_DEPLOYER_OBJECT_ID = <service-principal-object-id>
```

For local `terraform apply`, pass `azure_deployer_object_id` in `non-secret.tfvars` or `TF_VAR_azure_deployer_object_id` with your user or SP object ID.

### Container image tags

Terraform provisions Container Apps with placeholder images tagged `:qa` or `:prod` (`ghcr.io/<owner>/<repo>/relyo-api:<env>`). CI deploy workflows build, push `:qa`/`:prod` plus an immutable `:sha` tag, then update the running revision with the environment tag. Terraform ignores image changes after initial apply so deploys are not reverted.

### GitHub repository configuration

**Repository secrets** (Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `AZURE_CLIENT_ID` | App registration `appId` |
| `AZURE_TENANT_ID` | Azure AD tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Target subscription ID |

**Environment secrets** (Settings → Environments → `qa` / `prod`):

| Secret | Used at |
|---|---|
| `TF_VAR_postgres_admin_password` | `terraform plan` / `apply` |
| `TF_VAR_clerk_api_key` | `terraform plan` / `apply` |
| `TF_VAR_clerk_secret_key` | `terraform plan` / `apply` |
| `TF_VAR_clerk_publishable_key` | `terraform plan` / `apply` |
| `TF_VAR_clerk_jwks_url` | `terraform plan` / `apply` |
| `TF_VAR_xrpl_encryption_key` | `terraform plan` / `apply` |

**Environment variables** (Settings → Environments → `qa` / `prod`):

| Variable | Used at |
|---|---|
| `AZURE_DEPLOYER_OBJECT_ID` | `terraform plan` / `apply` — GitHub OIDC SP object ID for Key Vault Secrets Officer |

Non-sensitive Terraform inputs (`environment`, `alert_emails`, `budget_start_date`, custom domains, etc.) live in committed `non-secret.tfvars` per environment. Workflows also set `TF_VAR_ghcr_org` from `github.repository` so image paths match deploy workflows.

Workflow behaviour:

- **Pull request** to `qa` or `main` (with `infra/**` changes) → `terraform plan -var-file=non-secret.tfvars`
- **Push** to `qa` or `main` (merge) → `terraform apply -auto-approve -var-file=non-secret.tfvars`

## Layout

- `modules/` — reusable Terraform modules
- `envs/qa/` — QA environment root module
- `envs/prod/` — Prod environment root module
