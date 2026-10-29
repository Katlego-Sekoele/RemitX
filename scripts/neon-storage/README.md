# Neon Object Storage bootstrap

Neon Postgres is managed in `infra/data/`; **buckets and S3 credentials are not**
in the Neon Terraform providers yet. This script idempotently ensures a private
bucket and a named API credential exist on a branch.

## Inputs (environment)

| Variable | Required | Description |
|----------|----------|-------------|
| `NEON_API_KEY` | yes | Neon account API key |
| `NEON_PROJECT_ID` | yes | Neon project id |
| `NEON_BRANCH_ID` | yes | Branch id (or set `NEON_BRANCH_NAME`) |
| `NEON_BUCKET_NAME` | yes | e.g. `remitx-qa-kyc-documents` |
| `NEON_CREDENTIAL_NAME` | no | Default `remitx-api-kyc` |
| `NEON_STORAGE_MODE` | no | `verify` (default) or `bootstrap` |

- **verify** — bucket must exist; does not create credentials.
- **bootstrap** — create bucket if missing; create credential if the named one is absent (prints secrets once to stdout; pipe to CI secret update).

Requires `curl`, `jq`, and [Neon CLI](https://neon.com/docs/reference/cli-overview)
8.3 or newer (`npm install --global neon@latest`). The Deploy workflow installs
it on Node.js 22 before verification.

## CI

The Deploy workflow runs `scripts/neon-storage/ensure.sh` before Terraform when
`NEON_STORAGE_MODE` is set (default `verify` on rollout).
