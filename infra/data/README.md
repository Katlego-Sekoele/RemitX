# remitx-data (Terraform Cloud)

Neon Postgres branches and connection URLs for QA and Production.

Provider: **[neondatabase/neon](https://github.com/neondatabase/terraform-provider-neon)** (official). Requires Terraform **>= 1.14**.

Workspace: **`remitx-data`** (working directory `infra/data`). State lives in HCP Terraform; GCP workspaces read `database_urls` via remote state.

---

## Do you need to import?

| Situation | Import? |
|-----------|---------|
| Neon project and `qa` / `main` (or your `neon_*_branch_name` values) **already exist** in the console | **Yes — one-time manual import** (or `import` blocks + one apply). |
| **No** Neon project yet; Terraform should create everything | **No** — first `terraform apply` creates project, branches, and endpoints. |

**Deploy does not run import.** GitHub Actions only runs `terraform apply` on `infra/data` when that tree changes (or on `workflow_dispatch`). Until existing Neon resources are in state, a blind apply would try to **create** duplicate Neon objects.

Object storage (KYC buckets) is **not** in this stack — see [`scripts/neon-storage/`](../../scripts/neon-storage/).

---

## One-time import (existing Neon)

### 1. Prerequisites

- TFC workspace **`remitx-data`** exists (VCS root `infra/data`).
- Workspace variables (or local `TF_VAR_*` when running CLI):
  - `neon_api_key` (sensitive)
  - `tfe_token` (sensitive)
  - `hcp_organization`
  - `neon_org_id`
  - `neon_project_id` — the project you will import (same id used in import commands)
- Non-secrets: copy [`non-secret.tfvars.example`](non-secret.tfvars.example) → `non-secret.tfvars` (gitignored if you use it locally) or set in TFC. **`neon_qa_branch_name` / `neon_prod_branch_name`** must match Neon branch **names** (defaults `qa` / `main`; not git branches).

### 2. Collect Neon ids

You need **project id**, each branch’s **branch id**, and each branch’s **read-write endpoint id**.

**Console:** Project → Branches (branch id on each branch) → open branch → Endpoints (endpoint id for `read_write`).

**CLI** (same ids as GitHub `NEON_PROJECT_ID`, `NEON_QA_BRANCH_ID`, `NEON_PROD_BRANCH_ID` for storage verify):

```bash
export NEON_API_KEY="..."

neon projects list --output json | jq '.[] | {id, name}'

PROJECT_ID="your-project-id"

neon branches list --project-id "$PROJECT_ID" --output json \
  | jq '.branches[] | {id, name}'

neon endpoints list --project-id "$PROJECT_ID" --output json
```

Map names `qa` and `main` (or your tfvars) to `QA_BRANCH_ID`, `PROD_BRANCH_ID`, and the matching endpoint ids.

### 3. Import into TFC state

Run **once** from your machine (updates remote state in `remitx-data`). Use either **CLI import** or **import blocks** (next section). Shortcuts: `make -C infra data-init` and `make -C infra data-import-help`.

```bash
cd infra/data

export TF_CLOUD_ORGANIZATION="your-hcp-org"
export TF_TOKEN_app_terraform_io="..."   # TFC token
export TF_VAR_hcp_organization="$TF_CLOUD_ORGANIZATION"
export TF_VAR_neon_api_key="$NEON_API_KEY"
export TF_VAR_tfe_token="$TF_TOKEN_app_terraform_io"
export TF_VAR_neon_org_id="org-..."
export TF_VAR_neon_project_id="$PROJECT_ID"

terraform init

terraform import 'module.neon.neon_project.this' "$PROJECT_ID"
terraform import 'module.neon.neon_branch.qa' "$PROJECT_ID/$QA_BRANCH_ID"
terraform import 'module.neon.neon_branch.prod' "$PROJECT_ID/$PROD_BRANCH_ID"
terraform import 'module.neon.neon_endpoint.qa' "$PROJECT_ID/$QA_ENDPOINT_ID"
terraform import 'module.neon.neon_endpoint.prod' "$PROJECT_ID/$PROD_ENDPOINT_ID"

terraform plan   # expect small diff, not "create" for those five resources
```

| Terraform address | Import `id` |
|-------------------|-------------|
| `module.neon.neon_project.this` | `<project_id>` |
| `module.neon.neon_branch.qa` | `<project_id>/<qa_branch_id>` |
| `module.neon.neon_branch.prod` | `<project_id>/<prod_branch_id>` |
| `module.neon.neon_endpoint.qa` | `<project_id>/<qa_endpoint_id>` |
| `module.neon.neon_endpoint.prod` | `<project_id>/<prod_endpoint_id>` |

### 4. Import blocks (alternative)

Copy [`imports.tf.example`](imports.tf.example) to `imports.tf`, replace placeholders, commit, and run **one** `terraform apply` via TFC (or locally with remote backend). Remove `imports.tf` after a successful apply. Same end state as CLI `terraform import`.

### 5. Connection URLs (after import — separate from import)

Import does **not** require this step. Steps 1–4 (or import blocks) can finish with empty `database_urls` outputs.

You still need a working Postgres URL **somewhere** before rollouts succeed:

| Source | What it feeds | Required today? |
|--------|----------------|-----------------|
| GitHub `TF_VAR_database_url` + `MIGRATIONS_DATABASE_URL` (per `qa` / `prod` environment) | GCP Terraform `DATABASE_URL` on Cloud Run + Alembic migrate job | **Yes** — [deploy.yml](../../.github/workflows/deploy.yml) treats both as required |
| `remitx-data` output `database_urls` | `infra/gcp` via remote state when `TF_VAR_database_url` is empty | **No** for deploy while GitHub secrets are set; **yes** if you want TFC to own URLs and drop duplicate secrets later |

To populate **`database_urls`** on `remitx-data` (pick one approach per branch):

1. **Preferred:** set **`qa_role_name`** and **`prod_role_name`** on the workspace (role from Neon’s connection UI, e.g. `neondb_owner`). Optional: `qa_database_name` / `prod_database_name` if not `neondb`. Run `terraform apply`; Terraform reads passwords via the Neon provider and builds `postgresql+psycopg2://…` URLs in outputs.

2. **Interim:** set **`database_url_qa_override`** / **`database_url_prod_override`** on **`remitx-data` only** — not from per-environment GitHub deploy jobs (see [infra/README.md](../README.md#tfc-only-remitx-data)).

After apply, check sensitive output `database_urls` in TFC. If GitHub still holds the same URLs (current default), keep **`TF_VAR_database_url`** and **`MIGRATIONS_DATABASE_URL`** in sync with the branch you deploy until you rely on remote state alone.

---

## Greenfield (no import)

1. Set TFC variables as above (except you do not run import).
2. `terraform apply` creates `neon_project.this`, branches, and read-write endpoints.
3. Set `qa_role_name` / `prod_role_name` (or overrides) as in step 5 above.

---

## Ongoing automation

- **Deploy workflow:** `infra/data` apply only when `infra/data/**` changes or on manual dispatch — not on every app push unless data Terraform changed.
- **Do not** run `terraform init -upgrade` in CI.

---

## Related

- Parent checklist: [infra/README.md](../README.md) (*Manual vs automated*, *First-time apply order*).
- Clerk (optional import): [`../gcp/clerk.tf`](../gcp/clerk.tf), [`../gcp/imports.tf.example`](../gcp/imports.tf.example).
- KYC buckets: [`scripts/neon-storage/README.md`](../../scripts/neon-storage/README.md).
