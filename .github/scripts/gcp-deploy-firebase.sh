#!/usr/bin/env bash
# Build the SPA with VITE_* from Terraform outputs and deploy to Firebase Hosting.
set -euo pipefail

DEPLOY_ENV="${DEPLOY_ENV:?set DEPLOY_ENV to qa or prod}"

ROOT="${GITHUB_WORKSPACE:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$ROOT/infra/gcp"

export TF_WORKSPACE="remitx-gcp-${DEPLOY_ENV}"
terraform init -input=false

VITE_JSON="$(terraform output -json vite_env)"
export VITE_API_URL="$(echo "$VITE_JSON" | jq -r '.VITE_API_URL')"
export VITE_SITE_URL="$(echo "$VITE_JSON" | jq -r '.VITE_SITE_URL')"
export VITE_CLERK_PUBLISHABLE_KEY="$(echo "$VITE_JSON" | jq -r '.VITE_CLERK_PUBLISHABLE_KEY')"

cd "$ROOT/frontend"
npm ci
npm run build

TARGET="remitx-${DEPLOY_ENV}-web"
firebase use "${GCP_PROJECT_ID:?}" --add >/dev/null 2>&1 || firebase use "${GCP_PROJECT_ID:?}"
firebase deploy --only "hosting:${TARGET}" --project "${GCP_PROJECT_ID:?}"
