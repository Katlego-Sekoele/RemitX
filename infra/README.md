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
| `TF_VAR_postgres_admin_password` | `terraform apply` |
| `TF_VAR_clerk_api_key` | `terraform apply` |
| `TF_VAR_clerk_secret_key` | `terraform apply` |
| `TF_VAR_clerk_publishable_key` | `terraform apply` |
| `TF_VAR_clerk_jwks_url` | `terraform apply` |
| `TF_VAR_xrpl_encryption_key` | `terraform apply` |

Workflow behaviour:

- **Pull request** to `qa` or `main` (with `infra/**` changes) → `terraform plan`
- **Push** to `qa` or `main` (merge) → `terraform apply -auto-approve`

## Layout

- `modules/` — reusable Terraform modules
- `envs/qa/` — QA environment root module
- `envs/prod/` — Prod environment root module
