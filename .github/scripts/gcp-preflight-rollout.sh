#!/usr/bin/env bash
set -euo pipefail

missing=()
[ -n "${GOOGLE_CREDENTIALS:-}" ] || missing+=("GOOGLE_CREDENTIALS")
[ -n "${GCP_PROJECT_ID:-}" ] || missing+=("GCP_PROJECT_ID (variable)")
[ -n "${NEON_API_KEY:-}" ] || missing+=("NEON_API_KEY")
[ -n "${NEON_PROJECT_ID:-}" ] || missing+=("NEON_PROJECT_ID (variable)")
[ -n "${NEON_BRANCH_ID:-}" ] || missing+=("NEON_QA_BRANCH_ID / NEON_PROD_BRANCH_ID (variable)")

if [ ${#missing[@]} -gt 0 ]; then
  echo "::error::Missing for rollout on '${DEPLOY_ENV:-?}': ${missing[*]}"
  exit 1
fi
