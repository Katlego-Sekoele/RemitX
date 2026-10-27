# Plan 004: Keep one API instance up

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 94d8a57..HEAD -- infra/gcp/main.tf infra/gcp/modules/cloud_run_service/main.tf infra/gcp/modules/cloud_run_service/variables.tf`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: perf
- **Planned at**: commit `94d8a57`, 2026-10-27

## Why this matters

Steady-state slowness is round trips to Neon (plans 001 and 002). A
separate, larger delay hits the first request after the service has gone
idle: the API Cloud Run service sets `min_instance_count = 0`, so the
instance is shut down. The next request pays a Python cold start (the app
imports the whole route tree) and often a Neon compute wake
(`api/remitx_api/extensions.py` documents that Neon autosuspends and that
`pool_pre_ping` exists because of it). That first response is several
seconds, which is what people report as "the site takes forever" at the
start of a demo. The worker was already pinned to one instance for the
demo (`min_instance_count = 1` on module `worker`, commit `2b7d089`). The
API was not. This plan makes the same choice for the API only.

Cost: one always-on Cloud Run instance at the module default of 1 vCPU and
512Mi. There is a budget alert on production (`infra/gcp/main.tf` module
`billing`). Do not raise CPU, memory, or max instances in this plan.

## Current state

`infra/gcp/main.tf`:

```hcl
module "api" {
  source = "./modules/cloud_run_service"
  ...
  allow_unauthenticated = true
  min_instance_count    = 0
  ...
}

module "worker" {
  ...
  min_instance_count    = 1
  memory                = "1Gi"
  ...
}
```

`infra/gcp/modules/cloud_run_service/main.tf` passes `var.min_instance_count` into `scaling.min_instance_count`. CPU default is `1000m`, memory `512Mi` (`variables.tf`). The module does not set `startup_cpu_boost`. Leave that alone.

`gcp_region` defaults to `africa-south1` (`infra/gcp/variables.tf`).

Do not change the worker. Do not set `cpu_idle = false` (always-allocated CPU). That is a different billing mode and is not required to avoid a cold start once `min_instance_count` is 1. Cloud Run still throttles CPU between requests; the process stays resident, which is the cold-start fix.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Format check | `terraform fmt -check infra/gcp/main.tf` | exit 0, no diff |

`terraform validate` needs provider credentials and a backend. Do not run `terraform apply`. Do not run `terraform init` if it would touch remote state. `fmt -check` is the gate.

## Scope

**In scope**:
- `infra/gcp/main.tf` — the `module "api"` argument `min_instance_count` only

**Out of scope**:
- `module "worker"`, Firebase, billing, Neon (`infra/data/`), the Cloud Run module's variables, container images, env vars.
- Moving the Neon project to another region. That is a data migration. Do not start it. See the maintenance notes.

## Git workflow

- Branch: `katlego/api-min-instances-c907` if you are a Cursor cloud agent on this repo; otherwise `advisor/004-api-min-instances`.
- Commit message style, from `git log`: `Keep one API instance up`.
- Do NOT push or open a PR unless the operator instructed it.
- Do NOT apply Terraform.

## Steps

### Step 1: Pin the API to one instance

In `infra/gcp/main.tf`, on `module "api"` only, set `min_instance_count = 1`.

Add a one-line comment above that argument: cold start was the idle delay; the worker is already pinned the same way. Match the file's existing comment style (the file currently has almost none — a single trailing comment on the argument is enough, for example `min_instance_count = 1 # avoid cold starts; worker is already 1`).

**Verify**: `terraform fmt -check infra/gcp/main.tf` → exit 0. `rg "min_instance_count" infra/gcp/main.tf` shows `1` for both `module "api"` and `module "worker"`.

## Test plan

No automated test. The repository does not unit-test Terraform.

- Verification is `terraform fmt -check infra/gcp/main.tf` exiting 0, and the `rg` check above.
- After a human applies `infra/gcp`, the Cloud Run service `remitx-<env>-api` shows minimum instances 1. This plan does not apply it.

## Done criteria

- [ ] `module "api"` has `min_instance_count = 1`
- [ ] `module "worker"` is unchanged
- [ ] `terraform fmt -check infra/gcp/main.tf` exits 0
- [ ] No other files are modified
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `module "api"` already sets `min_instance_count` to something other than 0 (someone changed it).
- The module signature renamed `min_instance_count`.
- A fix seems to require editing `infra/data/` or a Neon URL.

## Maintenance notes

- If requests are still over a second when an instance is already warm, the remaining cost is distance to Neon, not cold start. `infra/data/modules/neon/main.tf` creates `neon_project` without a region. Neon has no Johannesburg region. Confirm the project region in the Neon console (do not paste connection strings into tickets). A region move is a new project and a data copy, not a one-line Terraform edit, and it is intentionally not this plan.
- Reviewer: this increases the always-on Cloud Run bill by one 1 vCPU / 512Mi instance per environment that applies the stack. QA and prod are separate applies.
