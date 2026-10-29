# Shared helpers for github-tf-env.sh and github-tf-env-check.sh (source, do not execute).

gh_var_upper() {
  printf '%s' "$1" | tr '[:lower:]' '[:upper:]'
}

# Terraform reads TF_VAR_<variable_name> where variable_name matches variables.tf (lowercase).
# GitHub may store TF_VAR_PLATFORM_WALLET_ADDRESS — normalize to TF_VAR_platform_wallet_address.
gh_var_tf_export_name() {
  local name="$1"
  local upper
  upper="$(gh_var_upper "$name")"
  case "$upper" in
    TF_VAR_*)
      local suffix="${upper#TF_VAR_}"
      suffix="$(printf '%s' "$suffix" | tr '[:upper:]' '[:lower:]')"
      printf 'TF_VAR_%s' "$suffix"
      ;;
    *)
      printf '%s' "$name"
      ;;
  esac
}

# Key for presence checks (uppercase for non-TF names like GCP_PROJECT_ID).
gh_var_presence_key() {
  local name="$1"
  local upper
  upper="$(gh_var_upper "$name")"
  case "$upper" in
    TF_VAR_*)
      gh_var_tf_export_name "$name"
      ;;
    *)
      printf '%s' "$upper"
      ;;
  esac
}

# gh variable list (bash 3.2 + set -u breaks "${empty[@]}"; avoid empty array expansion).
gh_var_gh_list() {
  if [ -n "${GITHUB_REPOSITORY:-}" ]; then
    gh variable list -R "$GITHUB_REPOSITORY" "$@"
  else
    gh variable list "$@"
  fi
}

# List variable names from repository + environment (dedupe left to caller).
gh_var_list_name_lines() {
  local deploy_env="$1"
  if [ -n "${GITHUB_VARIABLES_JSON:-}" ]; then
    printf '%s' "$GITHUB_VARIABLES_JSON" | jq -r 'keys[]'
    return
  fi
  gh_var_gh_list --json name -q '.[].name' 2>/dev/null || true
  gh_var_gh_list --env "$deploy_env" --json name -q '.[].name' 2>/dev/null || true
}
