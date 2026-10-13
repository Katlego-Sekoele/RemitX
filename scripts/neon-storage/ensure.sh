#!/usr/bin/env bash
# Idempotent Neon branch object storage: verify or bootstrap bucket + credential.
set -euo pipefail

MODE="${NEON_STORAGE_MODE:-verify}"
PROJECT_ID="${NEON_PROJECT_ID:-}"
BRANCH_ID="${NEON_BRANCH_ID:-}"
BRANCH_NAME="${NEON_BRANCH_NAME:-}"
BUCKET="${NEON_BUCKET_NAME:-}"
CREDENTIAL_NAME="${NEON_CREDENTIAL_NAME:-remitx-api-kyc}"
API_BASE="https://console.neon.tech/api/v2"

die() {
  echo "neon-storage: $*" >&2
  exit 1
}

if ! neon --version | grep -q "8.3"; then
  die "neon CLI version 8.3 or higher is required"
fi

require() {
  local name="$1" value="$2"
  [[ -n "$value" ]] || die "missing $name"
}

require NEON_API_KEY "${NEON_API_KEY:-}"
require NEON_PROJECT_ID "$PROJECT_ID"
require NEON_BUCKET_NAME "$BUCKET"

if [[ -z "$BRANCH_ID" && -n "$BRANCH_NAME" ]]; then
  command -v neon >/dev/null 2>&1 || die "NEON_BRANCH_NAME set but neon CLI not installed"
  BRANCH_ID="$(neon branches list --project-id "$PROJECT_ID" --output json \
    | jq -r --arg n "$BRANCH_NAME" '.[] | select(.name == $n) | .id' | head -1)"
  echo "neon-storage: branch ID for $BRANCH_NAME is $BRANCH_ID"
fi
require NEON_BRANCH_ID "$BRANCH_ID"

api() {
  local method="$1" path="$2"
  local data="${3:-}"
  if [[ -n "$data" ]]; then
    curl -fsS -X "$method" "$API_BASE$path" \
      -H "Authorization: Bearer $NEON_API_KEY" \
      -H "Content-Type: application/json" \
      -d "$data"
  else
    curl -fsS -X "$method" "$API_BASE$path" \
      -H "Authorization: Bearer $NEON_API_KEY"
  fi
}

storage_json="$(api GET "/projects/$PROJECT_ID/branches/$BRANCH_ID/storage")"
endpoint="$(echo "$storage_json" | jq -r '.s3_endpoint // empty')"
region="$(echo "$storage_json" | jq -r '.region // empty')"
[[ -n "$endpoint" ]] || die "object storage not enabled for branch $BRANCH_ID"

echo "neon-storage: endpoint=$endpoint region=$region"

bucket_exists=false
if command -v neon >/dev/null 2>&1; then
  BUCKET_LIST="$(neon buckets list --project-id "$PROJECT_ID" --branch "$BRANCH_ID" --output json | jq -r '.[] | .name')"
  echo "neon-storage: bucket list: $BUCKET_LIST"
  if echo "$BUCKET_LIST" | grep -q "^$BUCKET$"; then
    bucket_exists=true
  fi
else
  # REST list buckets (beta)
  if api GET "/projects/$PROJECT_ID/branches/$BRANCH_ID/buckets" \
    | jq -e --arg b "$BUCKET" '.buckets[]? | select(.name == $b)' >/dev/null 2>&1; then
    bucket_exists=true
  fi
fi

if [[ "$bucket_exists" == true ]]; then
  echo "neon-storage: bucket $BUCKET exists"
elif [[ "$MODE" == "bootstrap" ]]; then
  echo "neon-storage: creating bucket $BUCKET"
  if command -v neon >/dev/null 2>&1; then
    neon buckets create "$BUCKET" --access-level private \
      --project-id "$PROJECT_ID" --branch "$BRANCH_ID"
  else
    api POST "/projects/$PROJECT_ID/branches/$BRANCH_ID/buckets" \
      "$(jq -n --arg n "$BUCKET" '{name: $n, access_level: "private"}')" >/dev/null
  fi
else
  die "bucket $BUCKET missing (set NEON_STORAGE_MODE=bootstrap to create)"
fi

if [[ "$MODE" != "bootstrap" ]]; then
  exit 0
fi

command -v neon >/dev/null 2>&1 || die "bootstrap credential requires neon CLI"

if neon credentials list --project-id "$PROJECT_ID" --branch "$BRANCH_ID" --output json \
  | jq -e --arg n "$CREDENTIAL_NAME" '.[] | select(.name == $n)' >/dev/null; then
  echo "neon-storage: credential $CREDENTIAL_NAME already exists (not rotating)"
  exit 0
fi

echo "neon-storage: creating credential $CREDENTIAL_NAME"
neon credentials create \
  --name "$CREDENTIAL_NAME" \
  --scope storage:read \
  --scope storage:write \
  --project-id "$PROJECT_ID" \
  --branch "$BRANCH_ID" \
  --output json \
  | jq -r '
    "OBJECT_STORAGE_ACCESS_KEY_ID=\(.token_id)",
    "OBJECT_STORAGE_SECRET_ACCESS_KEY=\(.s3_secret_access_key)"
  '

echo "neon-storage: store the lines above in GitHub Environment secrets immediately" >&2
