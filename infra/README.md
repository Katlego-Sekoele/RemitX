# RemitX Infrastructure (Terraform)

GCP compute (Cloud Run API + worker, Firebase Hosting), **Upstash Redis**,
**Neon Postgres** (`infra/data/`), optional **Clerk** instance settings.
State on **HCP Terraform**. GCP region: `africa-south1` (Johannesburg).

Neon **object storage** (KYC) is not in the Neon Terraform providers; the deploy
workflow verifies buckets via `[scripts/neon-storage/](../scripts/neon-storage/)`.

Legacy Render stack (destroy after cutover): `[legacy-render/](legacy-render/)`.

**Local shortcuts:** [`Makefile`](Makefile) — `make infra` / `make -C infra help` (Terraform; `ENV=qa|prod` for GCP). App rollout: [`../deploy/Makefile`](../deploy/Makefile) (`make deploy`).

| Path                        | TFC workspace                               | Purpose                                                         |
| --------------------------- | ------------------------------------------- | --------------------------------------------------------------- |
| `data/`                     | `remitx-data`                               | Neon project/branches; `database_urls` outputs                  |
| `gcp/`                      | `remitx-gcp-qa`, `remitx-gcp-prod`          | Cloud Run, Firebase, Upstash, Artifact Registry, budgets (prod) |
| `gcp/environments/*.tfvars` | —                                           | Committed non-secrets per environment                           |
| `legacy-render/`            | `remitx-shared`, `remitx-qa`, `remitx-prod` | Former Render stack                                             |


---



## Manual vs automated



### You do once (outside the repo)


| Step                                                  | Where                                        | Notes                                                                                                                                                                                             |
| ----------------------------------------------------- | -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Create GCP project + link billing                     | Google Cloud Console                         | Project id → GitHub `GCP_PROJECT_ID`                                                                                                                                                              |
| Issue deploy credentials for the Terraform-managed SA | GCP / `gcloud`                               | After first `infra/gcp` apply: `terraform output -raw github_deploy_service_account_email` → create a **JSON key** or **Workload Identity Federation** for that SA → GitHub `GOOGLE_CREDENTIALS`. |
| Create HCP Terraform org + API token                  | [app.terraform.io](https://app.terraform.io) | → `TF_API_TOKEN`, `TF_CLOUD_ORGANIZATION`                                                                                                                                                         |
| Create TFC workspaces                                 | TFC UI                                       | `remitx-data` (VCS root `infra/data`), `remitx-gcp-qa` / `remitx-gcp-prod` (root `infra/gcp`)                                                                                                     |
| Set TFC variables for `remitx-data`                   | TFC workspace                                | See [TFC-only (](#tfc-only-remitx-data)`remitx-data`[)](#tfc-only-remitx-data) — **not** from deploy jobs                                                                                         |
| Neon project, `qa` + `main` branches, KYC buckets     | Neon Console                                 | **One-time Neon import** into `remitx-data` — [data/README.md](data/README.md); buckets via [`scripts/neon-storage/`](../scripts/neon-storage/)                                                |
| Upstash account + API key                             | Upstash Console                              | → GitHub secrets below                                                                                                                                                                            |
| Clerk QA + Production applications                    | Clerk Dashboard                              | Origins/redirect URLs; keys → GitHub                                                                                                                                                              |
| GitHub Environments `qa` and `prod`                   | GitHub repo settings                         | All secrets/variables in [catalog](#github-environments-catalog)                                                                                                                                  |
| DNS for custom domains                                | Registrar / Cloud DNS                        | After Firebase + Cloud Run URLs are known                                                                                                                                                         |
| Import existing Neon (and optional Clerk)             | Local or TFC run (not CI)                    | Neon: [data/README.md](data/README.md#import-existing-neon). Clerk: [gcp/imports.tf.example](gcp/imports.tf.example)                                                                             |


You do **not** create Artifact Registry, Cloud Run services, Firebase sites, or
Upstash databases in the console for normal operation — Terraform creates them on
apply.

### GitHub Actions does on every rollout (`deploy.yml`)


| Order | Job                            | What runs                                                                                                                 |
| ----- | ------------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| 1     | `ci`                           | Tests, Alembic on Postgres (see `ci.yml`)                                                                                 |
| 2     | `terraform`                    | Neon storage **verify** → `infra/data` apply **only if** `infra/data/`** changed (or manual dispatch) → `infra/gcp` apply |
| 3     | `migrate`                      | `alembic upgrade head` on Neon (`MIGRATIONS_DATABASE_URL`)                                                                |
| 4     | `deploy-api` / `deploy-worker` | Build/push Docker images to **Artifact Registry** (created by TF), `gcloud run deploy` with env from TF outputs           |
| 5     | `deploy-frontend`              | `npm run build` with `VITE_*` from TF → Firebase Hosting deploy                                                           |


Branch mapping: push to `main` → environment `qa`; push to `stable` → `prod`.

PRs on `infra/**`: Terraform **plan** only (no deploy). Push/manual: full rollout.

### Terraform creates (no console bootstrap)

On `infra/gcp` apply (per workspace):

- API enablement (Run, Artifact Registry, Firebase, Monitoring, …)
- **Artifact Registry** Docker repo (`artifact_registry_repository_id`, default `remitx`)
- Cloud Run services (image/env updated again by deploy jobs)
- Secret Manager versions for runtime credentials; Cloud Run receives them as
  secret-backed environment variables, never as plaintext service configuration
- Firebase project + Hosting site (+ custom domain resource when set in tfvars)
- Upstash Redis database per environment
- GCP billing budget + email channels (**prod workspace only**): **$10** planning target, emails every **$2** of project spend through **$100** by default (`monthly_budget_amount`, `budget_alert_step_usd`, `budget_alert_coverage_usd`; requires `BUDGET_ALERT_EMAILS` + `TF_VAR_billing_account_id`)
- Service accounts for API and worker; **GitHub deploy** SA `remitx-github-deploy` (created on first apply in a GCP project) plus Run / Artifact Registry / Firebase Hosting IAM on every workspace
- **One deploy SA per GCP project:** leave `github_deploy_service_account_email` empty (default) so Terraform creates it. If `remitx-gcp-qa` and `remitx-gcp-prod` target the **same** project, set that variable on the prod workspace to the email from `terraform output` after QA apply (so prod does not try to create a second SA)

On `infra/data` apply:

- Neon project/branches/endpoints (after import), connection URL outputs

---



## First-time apply order

1. Configure [GitHub](#github-environments-catalog) `qa` (and later `prod`).
2. **Import Neon** into `remitx-data` if the project already exists — [data/README.md](data/README.md#one-time-import-existing-neon). Then `terraform apply` `remitx-data`.
3. `terraform apply` `remitx-gcp-qa` (creates AR, Run, Firebase, Upstash, deploy SA, …).
4. Create a JSON key (or WIF) for `github_deploy_service_account_email` and set GitHub `GOOGLE_CREDENTIALS` on environment `qa` (and `prod` when that project is live). Example (JSON key):
  ```bash
   make -C infra gcp-init ENV=qa   # or: TF_WORKSPACE=remitx-gcp-qa terraform init (in infra/gcp)
   SA="$(terraform output -raw github_deploy_service_account_email)"
   gcloud iam service-accounts keys create github-deploy-key.json \
     --iam-account="$SA" --project="$GCP_PROJECT_ID"
  ```
   Paste the file contents into the environment secret (GOOGLE_CREDENTIALS); do not commit the key. If prod shares the QA project, reuse this same JSON.
5. Run **Deploy** workflow on `main` (or push app code) so images are pushed and
  Cloud Run env is applied.

The first GCP apply must use an existing project administrator (for example,
local user ADC) because the deploy service account does not exist yet. If the
service account already exists but predates the Terraform-management roles in
`gcp/iam.tf`, bootstrap those roles once as a project owner:

```bash
SA="remitx-github-deploy@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
for role in \
  roles/serviceusage.serviceUsageAdmin \
  roles/iam.serviceAccountAdmin \
  roles/resourcemanager.projectIamAdmin \
  roles/run.admin \
  roles/artifactregistry.admin \
  roles/firebase.admin \
  roles/monitoring.notificationChannelEditor
do
  gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
    --member="serviceAccount:${SA}" \
    --role="$role"
done
```

Terraform manages these project grants after that bootstrap. Production budget
resources additionally require `roles/billing.costsManager` on the **billing
account**, granted once outside this project stack.

Repeat with `remitx-gcp-prod` + `stable` for production. Same GCP project as QA: add `github_deploy_service_account_email = "remitx-github-deploy@<project-id>.iam.gserviceaccount.com"` to `prod.tfvars` and reuse the same `GOOGLE_CREDENTIALS`. Separate GCP projects: leave the variable empty on both.

---



## GitHub environments catalog

**Single source of truth:** non-secret **variables** and **secrets** for cloud deploy live in GitHub Environments `qa` / `prod` only — not in `common.tfvars` or duplicated product defaults in Terraform.

| Kind | How Terraform gets it |
|------|------------------------|
| **Variables** (fees, XRPL public config, `GCP_PROJECT_ID`, Neon ids, …) | [`scripts/github-tf-env.sh`](../scripts/github-tf-env.sh) at CI / `make -C infra gcp-plan` time → `TF_VAR_*` (uppercase `TF_VAR_FOO` on GitHub is normalized to Terraform’s `TF_VAR_foo`) |
| **Secrets** (Clerk, DB URL, API keys, …) | `deploy.yml` maps `secrets.*` → `TF_VAR_*` once (GitHub API cannot return secret values) |

Local: `make -C infra gcp-plan ENV=qa` loads **GitHub variables** via `gh` and **secrets** from repo-root `.env` when present (`scripts/github-tf-secrets-from-env.sh`). Or `eval "$(make -C infra --no-print-directory github-env ENV=qa)"` plus export any missing `TF_VAR_*`. `SKIP_GITHUB_ENV=1` / `SKIP_DOTENV_TF=1` to skip either source.

HCP Terraform **remote** runs only see variables you pass from the CLI/CI (`TF_VAR_*` in the job) or variables configured on the workspace — a bare `terraform plan` in the UI without those will fail on required inputs.

Committed [`gcp/environments/*.tfvars`](gcp/environments/) hold **infra shape** only (domains, buckets, images).

Create two [GitHub Actions environments](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment): `qa` (deploys from `main`) and `prod` (from `stable`). Values differ per environment (QA Clerk app vs Production, Neon branch URL, etc.).

**Legend:** **R** = required for deploy preflight / terraform job; **P** = prod only; **O** = optional (feature works degraded or off if unset).

### Secrets


| Name                                      | R   | Description                                                                                                                                                      |
| ----------------------------------------- | --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `TF_API_TOKEN`                            | ✓   | HCP Terraform API token (`TF_TOKEN_app_terraform_io` / `TF_VAR_tfe_token`).                                                                                      |
| `GOOGLE_CREDENTIALS`                      | ✓   | JSON key or WIF provider config for `remitx-github-deploy` (SA + IAM from Terraform; key/WIF created once outside TF).                                           |
| `NEON_API_KEY`                            | ✓   | Neon account API key; storage verify script + `TF_VAR_neon_api_key` on data apply.                                                                               |
| `BUDGET_ALERT_EMAILS`                     | P   | Comma-separated emails → `TF_VAR_budget_alert_emails` (GCP budget; prod TF only).                                                                                |
| `TF_VAR_upstash_api_key`                  | ✓   | Upstash Terraform provider API key.                                                                                                                              |
| `TF_VAR_database_url`                     | ✓   | SQLAlchemy Postgres URL for **this** environment’s Neon branch; GCP TF fallback until `remitx-data` remote state is wired; also passed as `TF_VAR_database_url`. |
| `MIGRATIONS_DATABASE_URL`                 | ✓   | Same URL as above for the **migrate** job (`alembic upgrade head`).                                                                                              |
| `TF_VAR_clerk_secret_key`                 | ✓   | Clerk instance secret (`sk_test_…` / `sk_live_…`); TF Clerk provider + runtime API/worker.                                                                       |
| `TF_VAR_xrpl_encryption_key`              | ✓   | Fernet key decrypting platform wallet material; API + worker.                                                                                                    |
| `TF_VAR_platform_wallet_seed_encrypted`   | ✓   | Encrypted XRPL treasury seed; **worker only**.                                                                                                                   |
| `TF_VAR_exchange_rate_api_key`            | ✓   | exchangerate-api.com key; **API only** (quotes).                                                                                                                 |
| `TF_VAR_object_storage_access_key_id`     | O   | Neon storage `token_id` (`nak_live_…`); **API only**. Without it, KYC routes return 503.                                                                         |
| `TF_VAR_object_storage_secret_access_key` | O   | Neon storage `s3_secret_access_key`; **API only**.                                                                                                               |
| `TF_VAR_evm_encryption_key`               | O   | EVM treasury encryption key; **worker only** when EVM settlement is enabled.                                                                                     |
| `TF_VAR_evm_treasury_key_encrypted`       | O   | Encrypted EVM treasury private key; **worker only**.                                                                                                             |




### Variables


| Name                                  | R   | Description                                                                                                                       |
| ------------------------------------- | --- | --------------------------------------------------------------------------------------------------------------------------------- |
| `TF_CLOUD_ORGANIZATION`               | ✓   | HCP Terraform organization name (also `TF_VAR_hcp_organization`).                                                                 |
| `GCP_PROJECT_ID`                      | ✓   | GCP project id → `TF_VAR_gcp_project_id` and all `gcloud` / Firebase deploys.                                                     |
| `GCP_ARTIFACT_REGISTRY_REPO`          | O   | Docker repository id in Artifact Registry (default `remitx` if unset; must match `artifact_registry_repository_id` in tfvars).    |
| `TF_VAR_billing_account_id`           | P   | GCP billing account id (`012345-ABCDEF-ABCDEF`) for budget resource.                                                              |
| `TF_VAR_clerk_publishable_key`        | ✓   | Clerk publishable key (`pk_test_…` / `pk_live_…`); TF output → `VITE_CLERK_PUBLISHABLE_KEY`.                                    |
| `TF_VAR_upstash_email`                | ✓   | Email on the Upstash account (Terraform provider auth; not sensitive).                                                            |
| `TF_VAR_monthly_budget_amount`        | P   | Monthly GCP **project** spend target in USD (default **10**; segment size for alerts; does not stop billing).                     |
| `TF_VAR_budget_alert_step_usd`        | P   | Budget email every N USD of **current** spend (default **2**; continues past the target).                                         |
| `TF_VAR_budget_alert_coverage_usd`    | P   | Last spend level for step alerts (default **100**; must be a multiple of `monthly_budget_amount`).                                |
| `NEON_ORG_ID`                         | ✓   | Neon organization id → `TF_VAR_neon_org_id` on data apply.                                                                        |
| `NEON_PROJECT_ID`                     | ✓   | Neon project id → storage verify + `TF_VAR_neon_project_id`.                                                                      |
| `NEON_QA_BRANCH_ID`                   | ✓*  | Branch id for QA storage verify when `deploy_env=qa`. Set on **both** environments so the workflow expression can resolve either. |
| `NEON_PROD_BRANCH_ID`                 | ✓*  | Branch id for prod storage verify when `deploy_env=prod`. Set on **both** environments.                                           |
| `TF_VAR_platform_wallet_address`      | ✓   | XRPL treasury classic address; API, worker, migrate treasury-funding migration.                                                   |
| `TF_VAR_xrpl_testnet_url`             | ✓   | XRPL JSON-RPC URL (testnet).                                                                                                      |
| `TF_VAR_uctusd_issuer`                | ✓   | UCTUSD issuer on testnet.                                                                                                         |
| `TF_VAR_uctusd_currency_code_hex`     | ✓   | Currency code on ledger (hex).                                                                                                    |
| `TF_VAR_uctusd_currency_code`         | ✓   | Currency code plain text (e.g. `UCTUSD`).                                                                                         |
| `TF_VAR_uctusd_trust_limit`           | ✓   | Trust line limit string.                                                                                                          |
| `TF_VAR_uctusd_distributor_address`   | ✓   | Distributor address on testnet.                                                                                                   |
| `TF_VAR_rate_fixing_interval_hours`   | ✓   | How long a fetched FX rate may be quoted.                                                                                         |
| `TF_VAR_max_rate_staleness_hours`     | ✓   | Max age of a stored rate if fetch fails.                                                                                          |
| `TF_VAR_quote_ttl_minutes`            | ✓   | Customer quote TTL.                                                                                                               |
| `TF_VAR_fixed_fee_zar`                | ✓   | Fixed send fee (ZAR).                                                                                                             |
| `TF_VAR_percentage_fee_rate`          | ✓   | Percentage fee (decimal).                                                                                                         |
| `TF_VAR_fx_margin_rate`               | ✓   | FX margin (decimal).                                                                                                              |
| `TF_VAR_cash_out_fee_rate`            | ✓   | Cash-out fee rate (decimal).                                                                                                      |
| `TF_VAR_min_cash_out_fee`             | ✓   | Minimum cash-out fee.                                                                                                             |
| `TF_VAR_daily_limit_zar_unverified`   | ✓   | Daily limit, unverified users (ZAR).                                                                                              |
| `TF_VAR_monthly_limit_zar_unverified` | ✓   | Monthly limit, unverified users (ZAR).                                                                                            |
| `TF_VAR_daily_limit_zar`              | ✓   | Daily limit, verified users (ZAR).                                                                                                |
| `TF_VAR_monthly_limit_zar`            | ✓   | Monthly limit, verified users (ZAR).                                                                                              |
| `TF_VAR_evm_treasury_address`         | O   | EVM treasury address on XRPL EVM testnet.                                                                                         |
| `TF_VAR_evm_rpc_url`                  | O   | EVM JSON-RPC URL.                                                                                                                 |
| `TF_VAR_evm_chain_id`                 | O   | EVM chain id (e.g. `1449000`).                                                                                                    |
| `TF_VAR_evm_explorer_url`             | O   | Block explorer base URL.                                                                                                          |
| `TF_VAR_uctusd_contract_address`      | O   | UCTUSD ERC-20 contract.                                                                                                           |
| `TF_VAR_uctusd_evm_decimals`          | O   | Token decimals on EVM.                                                                                                            |


Required on rollouts for the environment you deploy; storing both branch ids on both GitHub environments avoids duplicating workflow logic.

### Not in GitHub (committed or TFC)


| Source                                             | What                                                                                                        |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `infra/gcp/environments/qa.tfvars` / `prod.tfvars` | Domains, Neon storage endpoint/bucket/region, `git_branch`, placeholder Cloud Run images until first deploy |
| TFC workspace `remitx-gcp-*`                       | Can override any `TF_VAR_*` instead of GitHub                                                               |
| TFC workspace `remitx-data`                        | See below                                                                                                   |


---



## TFC-only (`remitx-data`)

Set on workspace `remitx-data` (not injected from deploy jobs for overrides):


| Variable                                  | Description                                                         |
| ----------------------------------------- | ------------------------------------------------------------------- |
| `neon_org_id`                             | Neon organization id                                                |
| `neon_project_id`                         | Existing project id (for import)                                    |
| `neon_qa_branch_name` / `neon_prod_branch_name` | Neon Postgres branch names (default `qa` / `main`; not git branches) |
| `qa_role_name` / `prod_role_name`         | Postgres role for built SQLAlchemy URLs                             |
| `qa_database_name` / `prod_database_name` | Default `neondb`                                                    |
| `database_url_qa_override`                | Optional; **only here**, never both branches from one GitHub secret |
| `database_url_prod_override`              | Optional; same                                                      |


Deploy applies `infra/data` when `infra/data/**` changes or on **workflow_dispatch** only.

---



## Neon object storage

- **Verify** (default on rollout): bucket must exist; see `scripts/neon-storage/README.md`.
- **Bootstrap** (new env): `NEON_STORAGE_MODE=bootstrap` once; copy printed credentials to `TF_VAR_object_storage_`* secrets.

Endpoint/bucket/region for Terraform live in `gcp/environments/*.tfvars`.

---



## Clerk (dashboard, not GitHub)

Per Clerk application (QA / Production): allowed origins, redirect URLs, and JWT
settings must include Terraform outputs (`frontend_url`, `api_url`). Optional:
import `clerk_application_settings` in `infra/gcp` (`manage_clerk_domains = true`).

Local development uses a separate Clerk **Development** app (`.env`), not GitHub.

---



## Destroy legacy Render

After GCP is live: `legacy-render/envs/prod` → `qa` → `shared`.