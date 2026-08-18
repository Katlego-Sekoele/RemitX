# RemitX Infrastructure (Terraform)

Terraform for **Azure** compute (Container Apps, Static Web Apps, Key Vault). **Neon** Postgres is provisioned outside Terraform; connection strings are passed as `TF_VAR_database_url`.

QA and Prod share modules under `modules/`; each environment has its own root under `envs/qa/` and `envs/prod/`.

**Design spec:** [docs/superpowers/specs/2026-08-18-azure-neon-deployment-design.md](../docs/superpowers/specs/2026-08-18-azure-neon-deployment-design.md)

## Layout

| Path | Purpose |
|------|---------|
| `modules/` | Reusable Terraform modules (no Azure Postgres — Neon replaces it) |
| `envs/qa/` | QA root module — git branch `qa` |
| `envs/prod/` | Production root module — git branch `main` |

## Tfvars files (both environments)

Each env directory has three tfvars-related files:

| File | Committed? | Purpose |
|------|------------|---------|
| `non-secret.tfvars` | Yes | Non-sensitive config used by **GitHub Actions** and recommended for local apply |
| `terraform.tfvars.example` | Yes | Template / documentation of all variables |
| `terraform.tfvars` | **No** (gitignored) | Optional local-only overrides — you rarely need this |

**CI and local apply both use `-var-file=non-secret.tfvars`.** Sensitive values are never in tfvars files; pass them as `TF_VAR_*` environment variables or GitHub environment secrets.

Edit `non-secret.tfvars` directly for values like `alert_emails`, `ghcr_org`, and `swa_location`. Only create `terraform.tfvars` if you prefer a private local file instead of shell exports.

---

## One-time setup (shared by QA and Prod)

Do this once before either environment is deployed.

### Terraform state backend

Default compute region is `spaincentral`. **Static Web Apps** use `swa_location` (`eastus2` by default) because SWA is unavailable in several compute regions and some SWA regions (e.g. West Europe) block new tenants.

Use a region allowed on your subscription if bootstrap fails.

```bash
az group create --name remitx-tfstate-rg --location spaincentral
az storage account create --name remitxtfstate --resource-group remitx-tfstate-rg --location spaincentral --sku Standard_LRS
az storage container create --name tfstate --account-name remitxtfstate
```

State keys are separate per environment: `qa.terraform.tfstate` and `prod.terraform.tfstate` in the same container.

### Neon

1. Create one Neon project (e.g. `remitx`).
2. Create two branches: **`qa`** and **`main`** (or `production`).
3. Save each branch connection string — you will use a different one per environment.

### Clerk

Create three applications in the [Clerk Dashboard](https://dashboard.clerk.com):

| Clerk app | Used by |
|-----------|---------|
| Development | Local `.env` |
| QA | QA stack |
| Production | Prod stack |

Allowed origins and redirect URLs are configured manually in Clerk (not Terraform).

### GitHub Actions OIDC

Register an Entra app with federated credentials for:

- `repo:<org>/RemitX:environment:qa`
- `repo:<org>/RemitX:environment:prod`

Grant **Contributor** on the subscription (or per resource group). Store on **each** GitHub environment (`qa` and `prod`):

| Secret / variable | Purpose |
|-------------------|---------|
| `AZURE_CLIENT_ID` | OIDC app client ID |
| `AZURE_TENANT_ID` | Tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Subscription ID |
| `TF_VAR_database_url` | Neon connection string **for that environment's branch** |
| `TF_VAR_clerk_secret_key` | Clerk secret key for that environment's app |
| `TF_VAR_clerk_publishable_key` | Clerk publishable key |
| `TF_VAR_clerk_jwks_url` | Clerk JWKS URL |
| `TF_VAR_xrpl_encryption_key` | XRPL encryption key (`python -c "import secrets; print(secrets.token_hex(32))"`) |

Workflow: `.github/workflows/deploy.yml` (Terraform + app deploys with `needs` ordering).

See [docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md) for the full bootstrap checklist.

---

## QA

**Git branch:** `qa`  
**Terraform root:** `infra/envs/qa/`  
**Neon branch:** `qa`  
**Clerk app:** QA  
**Workflow:** `.github/workflows/deploy.yml` (plan on PR, apply + deploy on push)

### QA-specific settings

| Setting | QA value |
|---------|----------|
| `api_min_replicas` | `0` (API scales to zero) |
| `swa_location` | `eastus2` (SWA not in `spaincentral`; change if region is ineligible) |
| Custom domains | Usually empty — default Azure URLs |
| Resource group | `remitx-qa-rg` |

### Configure QA

1. Edit committed config if needed:

   ```bash
   # infra/envs/qa/non-secret.tfvars
   # alert_emails, ghcr_org, swa_location
   ```

2. Add GitHub **environment secrets** on the `qa` environment (Neon **qa** branch URL, Clerk QA keys, etc.).

3. **Local apply** (optional — CI does this on push to `qa`):

   ```bash
   cd infra/envs/qa
   terraform init

   export TF_VAR_database_url='postgresql+psycopg2://REDACTED:REDACTED@REDACTED.neon.tech/neondb?sslmode=require'
   export TF_VAR_clerk_secret_key='sk_test_...'
   export TF_VAR_clerk_publishable_key='pk_test_...'
   export TF_VAR_clerk_jwks_url='https://<instance>.clerk.accounts.dev/.well-known/jwks.json'
   export TF_VAR_xrpl_encryption_key='...'

   terraform plan -var-file=non-secret.tfvars
   terraform apply -var-file=non-secret.tfvars
   ```

4. Push app changes to `qa` to trigger `deploy.yml` (API, worker, and/or frontend jobs as paths dictate).

### Deploy QA via CI (typical path)

```bash
git push origin qa
```

`deploy.yml` applies infra when `infra/**` changed, then runs deploy jobs for changed app paths.

### Destroy QA

```bash
cd infra/envs/qa
terraform destroy -var-file=non-secret.tfvars
```

Delete the Neon **qa** branch separately in the Neon console if you want to remove the database.

---

## Production

**Git branch:** `main`  
**Terraform root:** `infra/envs/prod/`  
**Neon branch:** `main` (or `production`)  
**Clerk app:** Production  
**Workflow:** `.github/workflows/deploy.yml` (prod environment)

Set up **after QA is working**. Prod uses separate Neon credentials, Clerk keys, and GitHub environment secrets.

### Prod-specific settings

| Setting | Prod value |
|---------|------------|
| `api_min_replicas` | `1` (API always on) |
| Custom domains | Set `api_custom_domain` and `swa_custom_domain` in `non-secret.tfvars` |
| Resource group | `remitx-prod-rg` |
| Subscription budget | Optional `enable_subscription_budget = true` in prod tfvars |

### Configure Prod

1. Edit committed config:

   ```bash
   # infra/envs/prod/non-secret.tfvars
   # api_custom_domain, swa_custom_domain, alert_emails, ghcr_org, ...
   ```

2. Add GitHub **environment secrets** on the `prod` environment (Neon **main** branch URL, Clerk Production keys — different from QA).

3. **Local apply** (optional):

   ```bash
   cd infra/envs/prod
   terraform init

   export TF_VAR_database_url='postgresql+psycopg2://REDACTED:REDACTED@REDACTED.neon.tech/neondb?sslmode=require'
   export TF_VAR_clerk_secret_key='sk_live_...'
   export TF_VAR_clerk_publishable_key='pk_live_...'
   export TF_VAR_clerk_jwks_url='https://<instance>.clerk.accounts.dev/.well-known/jwks.json'
   export TF_VAR_xrpl_encryption_key='...'

   terraform plan -var-file=non-secret.tfvars
   terraform apply -var-file=non-secret.tfvars
   ```

4. After apply, create DNS records from Terraform outputs:

   ```bash
   terraform output api_custom_domain_dns_records
   terraform output swa_custom_domain_dns_records
   ```

5. Update Clerk **Production** allowed origins with your live frontend and API URLs.

6. Merge to `main` / push to trigger prod deploy workflows.

### Destroy Prod

```bash
cd infra/envs/prod
terraform destroy -var-file=non-secret.tfvars
```

Delete the Neon **main** branch separately in the Neon console.

---

## Billing alerts

Per-dollar Azure billing alerts fire on **Actual** spend at each whole dollar up to `monthly_budget_cap` (default $20). The module creates segment budgets (Azure allows 5 thresholds per budget).

- Resource group budgets are created for **both** QA and Prod resource groups.
- Subscription-wide alerts are optional in prod only.
- Neon and Clerk costs are **not** included in Azure budgets.

Set `budget_start_date` to the first day of the current month in ISO8601 (e.g. `2026-08-01T00:00:00Z`).

## Container image tags

Terraform creates API and worker Container Apps with a **public bootstrap image** (`mcr.microsoft.com/k8se/quickstart:latest`) because GHCR images do not exist yet and private packages cannot be pulled during first apply.

After `terraform apply`, push a change under `api/**` (or re-run deploy) so `deploy.yml` builds and pushes:

- `ghcr.io/<owner>/<repo>/remitx-api:qa` (or `:prod`)
- `ghcr.io/<owner>/<repo>/remitx-worker:qa` (or `:prod`)

…and updates each Container App revision. Terraform ignores image drift after initial provisioning (`lifecycle.ignore_changes` on the container image).

## Troubleshooting apply failures

### Key Vault: "Caller is not allowed to change permission model"

The first failed apply created `remitx-*-kv` with **RBAC** enabled. Terraform now uses **access policies**, which requires a fresh vault — Azure cannot convert permission models with a Contributor-only identity.

Delete the vault, purge soft-delete, drop it from state, then re-apply:

```bash
az keyvault delete --name remitx-qa-kv --resource-group remitx-qa-rg
az keyvault purge --name remitx-qa-kv

cd infra/envs/qa
terraform state rm 'module.key_vault.azurerm_key_vault.this'
terraform apply -var-file=non-secret.tfvars
```

Or replace in one step after deleting the vault in Azure (see above):

```bash
terraform apply -replace='module.key_vault.azurerm_key_vault.this' -var-file=non-secret.tfvars
```

### Static Web Apps: "region is currently not accepting new customers"

Azure blocks new SWA deployments in some regions (e.g. West Europe). Edit `swa_location` in `non-secret.tfvars` to another [supported SWA region](https://learn.microsoft.com/azure/static-web-apps/overview#regions): `eastus2`, `westus2`, `centralus`, or `eastasia`.
