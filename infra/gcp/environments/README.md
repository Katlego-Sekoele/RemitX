# Environment tfvars

Committed **infrastructure shape only** (domains, Neon storage paths, placeholder
images, `environment` / `git_branch`). **Runtime config and secrets** live in
GitHub Environments `qa` / `prod` — see [infra/README.md](../../README.md#github-environments-catalog).

`make -C infra gcp-plan ENV=qa` and CI load variables via
[`scripts/github-tf-env.sh`](../../../scripts/github-tf-env.sh) (`gh` CLI).

| File | Purpose |
|------|---------|
| [`qa.tfvars`](qa.tfvars) / [`prod.tfvars`](prod.tfvars) | Per-env infra constants not stored in GitHub |

Plan/apply use `-var-file=environments/$(ENV).tfvars` plus GitHub-sourced `TF_VAR_*`.
