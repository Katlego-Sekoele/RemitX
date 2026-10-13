#!/usr/bin/env bash
# Fail if required GitHub Environment variables are missing (names only; case-insensitive for TF_VAR_*).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=github-tf-env-lib.sh
source "${SCRIPT_DIR}/github-tf-env-lib.sh"

DEPLOY_ENV="${1:?usage: github-tf-env-check.sh <qa|prod>}"

# Canonical keys after normalization (see github-tf-env-lib.sh).
required_keys=(
  GCP_PROJECT_ID
  TF_CLOUD_ORGANIZATION
  NEON_ORG_ID
  NEON_PROJECT_ID
  TF_VAR_platform_wallet_address
  TF_VAR_xrpl_testnet_url
  TF_VAR_uctusd_issuer
  TF_VAR_uctusd_currency_code_hex
  TF_VAR_uctusd_currency_code
  TF_VAR_uctusd_trust_limit
  TF_VAR_uctusd_distributor_address
  TF_VAR_rate_fixing_interval_hours
  TF_VAR_max_rate_staleness_hours
  TF_VAR_quote_ttl_minutes
  TF_VAR_fixed_fee_zar
  TF_VAR_percentage_fee_rate
  TF_VAR_fx_margin_rate
  TF_VAR_cash_out_fee_rate
  TF_VAR_min_cash_out_fee
  TF_VAR_daily_limit_zar_unverified
  TF_VAR_monthly_limit_zar_unverified
  TF_VAR_daily_limit_zar
  TF_VAR_monthly_limit_zar
  TF_VAR_clerk_publishable_key
  TF_VAR_upstash_email
)

if [ "$DEPLOY_ENV" = "qa" ]; then
  required_keys+=(NEON_QA_BRANCH_ID)
elif [ "$DEPLOY_ENV" = "prod" ]; then
  required_keys+=(TF_VAR_billing_account_id)
  required_keys+=(NEON_PROD_BRANCH_ID)
fi

present=""
while IFS= read -r name; do
  [ -z "$name" ] && continue
  key="$(gh_var_presence_key "$name")"
  present="${present}${key}"$'\n'
done < <(gh_var_list_name_lines "$DEPLOY_ENV" | sort -u)

missing=()
for key in "${required_keys[@]}"; do
  if ! grep -qx "$key" <<<"$present"; then
    missing+=("$key")
  fi
done

if [ ${#missing[@]} -gt 0 ]; then
  echo "::error::Missing GitHub variables on '${DEPLOY_ENV}' (repo + environment, after normalization): ${missing[*]}"
  exit 1
fi
