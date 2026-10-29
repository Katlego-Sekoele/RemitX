#!/usr/bin/env bash
# GitHub Environment *variables* → Terraform / workflow env.
# Secrets cannot be read from GitHub; deploy.yml maps secrets into the job once.
#
# TF_VAR_* names are normalized to lowercase suffixes (GitHub may use TF_VAR_PLATFORM_WALLET_ADDRESS).
#
# Usage:
#   eval "$(make -C infra --no-print-directory github-env ENV=qa)"
#   ./scripts/github-tf-env.sh qa >> "$GITHUB_ENV"    # GitHub Actions

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=github-tf-env-lib.sh
source "${SCRIPT_DIR}/github-tf-env-lib.sh"

DEPLOY_ENV="${1:?usage: github-tf-env.sh <qa|prod> [--shell]}"
MODE="github_env"
if [ "${2:-}" = "--shell" ]; then
  MODE="shell"
fi

if [ -n "${GITHUB_VARIABLES_JSON:-}" ]; then
  # Actions has already resolved organization, repository, and selected
  # environment variables into the `vars` context. Using it avoids an API
  # round-trip that GITHUB_TOKEN may not be permitted to make.
  json="$(printf '%s' "$GITHUB_VARIABLES_JSON" | jq '[to_entries[] | {name: .key, value: .value}]')"
else
  if ! command -v gh >/dev/null 2>&1; then
    echo "gh CLI is required (https://cli.github.com/)" >&2
    exit 1
  fi

  repo_json="$(gh_var_gh_list --json name,value)"
  env_json="$(gh_var_gh_list --env "$DEPLOY_ENV" --json name,value)"
  json="$(jq -n --argjson repo "$repo_json" --argjson env "$env_json" '$env + $repo | unique_by(.name)')"
fi
if [ -z "$json" ] || [ "$json" = "[]" ] || [ "$json" = "null" ]; then
  echo "No GitHub variables for environment '${DEPLOY_ENV}' (repo + environment)" >&2
  exit 1
fi

emit() {
  local name="$1"
  local value="$2"
  if [ "$MODE" = "shell" ]; then
    printf 'export %s\n' "$(printf '%s=%q' "$name" "$value")"
  else
    {
      echo "${name}<<EOF"
      echo "$value"
      echo "EOF"
    }
  fi
}

while IFS=$'\t' read -r name value; do
  upper="$(gh_var_upper "$name")"
  case "$upper" in
    GCP_PROJECT_ID)
      emit "TF_VAR_gcp_project_id" "$value"
      ;;
    TF_CLOUD_ORGANIZATION)
      emit "TF_VAR_hcp_organization" "$value"
      emit "TF_CLOUD_ORGANIZATION" "$value"
      ;;
    NEON_ORG_ID)
      emit "TF_VAR_neon_org_id" "$value"
      ;;
    NEON_PROJECT_ID)
      emit "TF_VAR_neon_project_id" "$value"
      ;;
    TF_VAR_*)
      emit "$(gh_var_tf_export_name "$name")" "$value"
      ;;
    *)
      emit "$name" "$value"
      ;;
  esac
done < <(printf '%s' "$json" | jq -r '.[] | [.name, .value] | @tsv')
