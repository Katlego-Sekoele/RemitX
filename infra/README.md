# RemitX Infrastructure (Terraform)

Terraform for **Render** compute (API + worker web services, static frontend)
and one shared Key Value instance. Provider:
[`render-oss/render` 1.9.1](https://registry.terraform.io/providers/render-oss/render/latest/docs).
That version cannot update free web services (`maintenance_mode` on every
PATCH; [issue #80](https://github.com/render-oss/terraform-provider-render/issues/80)).
`env_vars` / `custom_domains` are ignored on `render_web_service`; env vars
are synced after apply by `.github/scripts/render-sync-env.sh`.
**Neon** Postgres stays outside Terraform; connection strings are passed as
`TF_VAR_database_url`.

**Design spec:** [docs/superpowers/specs/2026-09-12-render-migration-design.md](../docs/superpowers/specs/2026-09-12-render-migration-design.md)

Azure roots used for teardown live in [legacy-azure/](legacy-azure/README.md).

## Layout

| Path | Purpose |
|------|---------|
| `shared/` | HCP workspace `remitx-shared` — project + Key Value (`./modules`) |
| `envs/qa/` | QA — git branch `main`, Redis DB `/0` (`./modules`) |
| `envs/prod/` | Production — git branch `stable`, Redis DB `/1` (`./modules`) |
| `legacy-azure/` | Destroy-only Azure stack |

Modules live **inside** each root (`./modules/...`), not as `../modules`. HCP
remote plans only upload the workspace directory, so a parent path is missing
on the runner.

## Plans (Hobby / free)

Every Render compute resource uses `plan = free`. There is no
`render_background_worker`. The worker is a web service that serves
`GET /health` and runs Celery. Auto-deploy is off; GitHub Actions triggers
deploys after migrate.

Hobby includes two custom domains: Production `remitx.tech` and QA
`qa.remitx.tech`. APIs stay on `*.onrender.com`.

## One-time bootstrap

1. Create a Render Hobby workspace. Note the owner id (`usr-…` or `tea-…`)
   and create an API key.
2. Create an HCP Terraform organization (any name) and three CLI-driven
   workspaces: `remitx-shared`, `remitx-qa`, `remitx-prod`. Create an HCP
   API token. Export the org name as `TF_CLOUD_ORGANIZATION` (and the same
   value as `TF_VAR_hcp_organization` for remote state).
3. Put these on the GitHub `qa` and `prod` environments:

| Name | Kind | Purpose |
|------|------|---------|
| `TF_CLOUD_ORGANIZATION` | **Variable** | HCP org name (`cloud` blocks cannot take Terraform variables) |
| `TF_API_TOKEN` | Secret | HCP Terraform token |
| `RENDER_API_KEY` | Secret | Render API key (mapped to `TF_VAR_render_api_key` for HCP) |
| `RENDER_OWNER_ID` | Secret | Render owner id (mapped to `TF_VAR_render_owner_id` for HCP) |
| `TF_VAR_database_url` | Secret | Neon URL for that environment (SQLAlchemy form) |
| `MIGRATIONS_DATABASE_URL` | Secret | Same Neon URL (Actions is off-Render) |
| `TF_VAR_clerk_secret_key` | Secret | Clerk secret key |
| `TF_VAR_clerk_publishable_key` | Secret | Clerk publishable key |
| `TF_VAR_xrpl_encryption_key` | Secret | Fernet key that decrypts the treasury seed. Already required. API and worker. |
| `TF_VAR_platform_wallet_seed_encrypted` | Secret | Encrypted treasury seed (`PLATFORM_WALLET_SEED_ENCRYPTED`). Worker only. |
| `TF_VAR_exchange_rate_api_key` | Secret | exchangerate-api.com key. API only. |
| `TF_VAR_object_storage_access_key_id` | Secret | Neon Object Storage key for the KYC document bucket (optional — unset leaves only the document routes answering 503) |
| `TF_VAR_object_storage_secret_access_key` | Secret | Its secret (optional, same) |
| `TF_VAR_platform_wallet_address` | **Variable** | Treasury XRPL classic address. API and worker. |
| `TF_VAR_xrpl_testnet_url` | **Variable** | Testnet JSON-RPC URL, e.g. `https://s.altnet.rippletest.net:51234/` |
| `TF_VAR_uctusd_issuer` | **Variable** | UCTUSD issuer address |
| `TF_VAR_uctusd_currency_code_hex` | **Variable** | On-chain currency code, hex |
| `TF_VAR_uctusd_currency_code` | **Variable** | On-chain currency code, plain text (`UCTUSD`) |
| `TF_VAR_uctusd_trust_limit` | **Variable** | Trust-line limit (`1000000` in `.env.example`) |
| `TF_VAR_uctusd_distributor_address` | **Variable** | UCTUSD distributor address |
| `TF_VAR_rate_fixing_interval_hours` | **Variable** | How long a fetched rate may be quoted |
| `TF_VAR_max_rate_staleness_hours` | **Variable** | Oldest stored rate a failed fetch may reuse |
| `TF_VAR_quote_ttl_minutes` | **Variable** | How long a customer quote is honoured |
| `TF_VAR_fixed_fee_zar` | **Variable** | Fixed send fee in ZAR |
| `TF_VAR_percentage_fee_rate` | **Variable** | Percentage fee as a decimal (`0.005`) |
| `TF_VAR_fx_margin_rate` | **Variable** | FX spread as a decimal (`0.01`) |
| `TF_VAR_cash_out_fee_rate` | **Variable** | Cash-out fee as a decimal (`0.0075`) |
| `TF_VAR_min_cash_out_fee` | **Variable** | Floor on the cash-out fee (`0.01`); the smallest withdrawal is this plus `0.01` |
| `TF_VAR_daily_limit_zar_unverified` | **Variable** | Unverified daily limit, ZAR |
| `TF_VAR_monthly_limit_zar_unverified` | **Variable** | Unverified monthly limit, ZAR |
| `TF_VAR_daily_limit_zar` | **Variable** | Verified daily limit, ZAR |
| `TF_VAR_monthly_limit_zar` | **Variable** | Verified monthly limit, ZAR |
| `TF_VAR_evm_encryption_key` | Secret | Fernet key that decrypts the EVM treasury key (`EVM_ENCRYPTION_KEY`). Optional for now. **Worker only.** |
| `TF_VAR_evm_treasury_key_encrypted` | Secret | Encrypted EVM treasury key (`EVM_TREASURY_KEY_ENCRYPTED`). Optional for now. **Worker only.** |
| `TF_VAR_evm_treasury_address` | **Variable** | Treasury Wallet EVM address on XRPL EVM Testnet. Optional for now. API and worker. |
| `TF_VAR_evm_rpc_url` | **Variable** | XRPL EVM Testnet JSON-RPC URL (`https://rpc.testnet.xrplevm.org`). Optional for now. API and worker. |
| `TF_VAR_evm_chain_id` | **Variable** | Chain id (`1449000`). Optional for now. API and worker. |
| `TF_VAR_evm_explorer_url` | **Variable** | Explorer base URL (`https://explorer.testnet.xrplevm.org`). Optional for now. API and worker. |
| `TF_VAR_uctusd_contract_address` | **Variable** | UCTUSD ERC-20 contract address (value in `.env.example`). Optional for now. API and worker. |
| `TF_VAR_uctusd_evm_decimals` | **Variable** | UCTUSD ERC-20 decimals (`18`). Optional for now. API and worker. |

The **Variable** rows are GitHub environment variables (`vars`), not secrets.
Quote, fee, and limit values land on the API. The XRPL rows land on the API
and the worker, except `TF_VAR_platform_wallet_seed_encrypted`, which lands
on the worker only. Copy the non-secret values from `.env.example` when QA
and Production should match local. Add the same names to both the `qa` and
`prod` environments. A rollout with any of them empty fails in the
`terraform` job before apply.

The XRPL EVM Testnet is replacing the XRP Ledger Testnet for on-chain
settlement; the `TF_VAR_evm_*` and `TF_VAR_uctusd_contract_address` /
`TF_VAR_uctusd_evm_decimals` rows are its inputs. They are the exception to the
rule above: **optional** and not in the required-input check, because the
GitHub values do not exist yet. An unset one reaches Terraform as `""` and is
left out of the services' environment rather than set to an empty string. The
two EVM secrets land on the **worker only**, never on the API, and only once
they are set. Add them to the required check in `deploy.yml` once they are set
in both environments.

4. Apply **shared first**. QA and Production read `remitx-shared` via
   `terraform_remote_state`. Shared apply authorizes those workspaces as
   remote-state consumers (HCP otherwise returns *forbidden*). CI always
   applies shared, then plans (PR) or applies (push, manual run) the env root.
   The `terraform` job runs on **every** rollout, not only when `infra/**`
   changed, so a merged fix or a manual **Actions → Deploy → Run workflow**
   converges the stack without an infra commit.

   Until that apply lands, you can grant the same access in HCP:
   **remitx-shared → Settings → General → Remote state sharing →**
   share with `remitx-qa` and `remitx-prod`.

```bash
export TF_CLOUD_ORGANIZATION="<your-hcp-org>"
export TF_VAR_hcp_organization="$TF_CLOUD_ORGANIZATION"
export TF_VAR_render_api_key="$RENDER_API_KEY"
export TF_VAR_render_owner_id="$RENDER_OWNER_ID"
export TF_VAR_tfe_token="$TF_API_TOKEN"

cd infra/shared && terraform init && terraform apply -var-file=non-secret.tfvars
cd infra/envs/qa && terraform init && terraform apply -var-file=non-secret.tfvars
cd infra/envs/prod && terraform init && terraform apply -var-file=non-secret.tfvars
```

5. Destroy Azure from [legacy-azure/](legacy-azure/README.md). Do not delete Neon.

## DNS (Production)

After apply, point `remitx.tech` at the frontend hostname in
`terraform output` from `infra/envs/prod`. Verify in the Render dashboard
(managed TLS). Update Clerk Production allowed origins. The API is the
`*.onrender.com` URL — do not set `VITE_API_URL` to `api.remitx.tech`.

## Worker wake

Terraform sets `WORKER_WAKE_URL` on the API to the worker's public `/health`.
Leave it unset locally. A future always-on worker can drop the variable.
