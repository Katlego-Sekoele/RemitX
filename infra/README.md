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

## Layout

- `modules/` — reusable Terraform modules
- `envs/qa/` — QA environment root module
- `envs/prod/` — Prod environment (added in a later task)
