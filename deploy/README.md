# GCP deploy (Makefile)

Rollout steps after Terraform and migrations: preflight, Docker push, Cloud Run,
Firebase Hosting. **Infrastructure** (Terraform, Neon storage verify) is
[`../infra/Makefile`](../infra/Makefile).

From the repo root:

```bash
export DEPLOY_ENV=qa GCP_PROJECT_ID=... GOOGLE_CREDENTIALS=... # etc.
make -C deploy help
make -C deploy preflight
make -C deploy push-api IMAGE_TAG=$(git rev-parse HEAD)
make -C deploy deploy-cloud-run SERVICE_ROLE=api IMAGE=...
```

GitHub Actions `deploy.yml` uses the same targets on the api / worker /
frontend jobs.
