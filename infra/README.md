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
| `RENDER_API_KEY` | Render API key (mapped to `TF_VAR_render_api_key` for HCP) |
| `RENDER_OWNER_ID` | Render owner id (mapped to `TF_VAR_render_owner_id` for HCP) |
| `TF_VAR_database_url` | Neon URL for that environment (SQLAlchemy form) |
| `MIGRATIONS_DATABASE_URL` | Same Neon URL (Actions is off-Render) |
| `TF_VAR_clerk_secret_key` | Clerk secret key |
| `TF_VAR_clerk_publishable_key` | Clerk publishable key |
| `TF_VAR_xrpl_encryption_key` | XRPL encryption key |

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
