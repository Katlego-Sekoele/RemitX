#!/usr/bin/env bash
# Deploy one Cloud Run service from Terraform outputs (image + env).
set -euo pipefail

SERVICE_ROLE="${SERVICE_ROLE:?set SERVICE_ROLE to api or worker}"
DEPLOY_ENV="${DEPLOY_ENV:?set DEPLOY_ENV to qa or prod}"
GCP_REGION="${GCP_REGION:-africa-south1}"

ROOT="${GITHUB_WORKSPACE:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$ROOT/infra/gcp"

export TF_WORKSPACE="remitx-gcp-${DEPLOY_ENV}"
terraform init -input=false

case "$SERVICE_ROLE" in
  api)
    SERVICE_NAME="remitx-${DEPLOY_ENV}-api"
    IMAGE="${IMAGE:-$(terraform output -raw api_container_image)}"
    ENV_JSON="$(terraform output -json api_env_vars)"
    SECRET_ENV_JSON="$(terraform output -json api_secret_env_vars)"
    ;;
  worker)
    SERVICE_NAME="remitx-${DEPLOY_ENV}-worker"
    IMAGE="${IMAGE:-$(terraform output -raw worker_container_image)}"
    ENV_JSON="$(terraform output -json worker_env_vars)"
    SECRET_ENV_JSON="$(terraform output -json worker_secret_env_vars)"
    ;;
  *)
    echo "unknown SERVICE_ROLE=$SERVICE_ROLE" >&2
    exit 1
    ;;
esac

ENV_JSON_FILE="$(mktemp)"
ENV_FILE="$(mktemp)"
echo "$ENV_JSON" >"$ENV_JSON_FILE"
python3 "$ROOT/.github/scripts/gcp-write-cloud-run-env.py" "$ENV_JSON_FILE" "$ENV_FILE"
SET_SECRETS="$(printf '%s' "$SECRET_ENV_JSON" | jq -r \
  'to_entries | map("\(.key)=\(.value):latest") | join(",")')"

gcloud run deploy "$SERVICE_NAME" \
  --project "${GCP_PROJECT_ID:?}" \
  --region "$GCP_REGION" \
  --image "$IMAGE" \
  --env-vars-file "$ENV_FILE" \
  --set-secrets "$SET_SECRETS" \
  --port 4200 \
  --allow-unauthenticated

rm -f "$ENV_JSON_FILE" "$ENV_FILE"
