#!/usr/bin/env bash
# Map repo-root .env → TF_VAR_* for local `make -C infra gcp-plan` (secrets only).
# Skips any TF_VAR_* already set (GitHub variables / exports win). Does not echo values.
#
# Usage (from Makefile): eval "$(./scripts/github-tf-secrets-from-env.sh)"

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

export_if_empty() {
  local tf_name="$1"
  local value="$2"
  [ -z "$value" ] && return 0
  if [ -n "${!tf_name:-}" ]; then
    return 0
  fi
  printf 'export %s\n' "$(printf '%s=%q' "$tf_name" "$value")"
}

if [ ! -f "$ENV_FILE" ]; then
  exit 0
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

export_if_empty TF_VAR_database_url "${DATABASE_URL:-}"
export_if_empty TF_VAR_gcloud_application_default_credentials_json "${GOOGLE_CREDENTIALS:-}"
export_if_empty TF_VAR_clerk_secret_key "${CLERK_SECRET_KEY:-}"
export_if_empty TF_VAR_clerk_publishable_key "${VITE_CLERK_PUBLISHABLE_KEY:-}"
export_if_empty TF_VAR_xrpl_encryption_key "${XRPL_ENCRYPTION_KEY:-}"
export_if_empty TF_VAR_platform_wallet_seed_encrypted "${PLATFORM_WALLET_SEED_ENCRYPTED:-}"
export_if_empty TF_VAR_exchange_rate_api_key "${EXCHANGE_RATE_API_KEY:-}"
export_if_empty TF_VAR_object_storage_access_key_id "${OBJECT_STORAGE_ACCESS_KEY_ID:-}"
export_if_empty TF_VAR_object_storage_secret_access_key "${OBJECT_STORAGE_SECRET_ACCESS_KEY:-}"
export_if_empty TF_VAR_evm_encryption_key "${EVM_ENCRYPTION_KEY:-}"
export_if_empty TF_VAR_evm_treasury_key_encrypted "${EVM_TREASURY_KEY_ENCRYPTED:-}"
export_if_empty TF_VAR_evm_stokvel_admin_key_encrypted "${EVM_STOKVEL_ADMIN_KEY_ENCRYPTED:-}"
export_if_empty TF_VAR_upstash_email "${UPSTASH_EMAIL:-}"
export_if_empty TF_VAR_upstash_api_key "${UPSTASH_API_KEY:-}"
