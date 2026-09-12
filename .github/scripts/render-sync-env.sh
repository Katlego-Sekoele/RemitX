#!/usr/bin/env bash
# Patch environment variables on a Render service via the public API.
#
# render-oss/render 1.9.1 sends maintenance_mode on every
# render_web_service update, and Render rejects that field on free
# plans. This script is the update path for env vars on those services.
#
# Usage:
#   SERVICE_NAME=remitx-qa-api ./render-sync-env.sh KEY=VALUE [KEY=VALUE ...]
#
# PUT /v1/services/{id}/env-vars/{key} updates one key and does not
# replace the rest. It does not deploy; the deploy jobs do that.
set -euo pipefail

: "${RENDER_API_KEY:?RENDER_API_KEY is not set. Add it to the GitHub environment for this deploy.}"
: "${SERVICE_NAME:?SERVICE_NAME is not set.}"

# Pairs come from argv (KEY=VALUE) or RENDER_SYNC_ENV_JSON (object).
if [ -n "${RENDER_SYNC_ENV_JSON:-}" ]; then
  mapfile -t pairs < <(
    python3 -c '
import json, os, sys
vals = json.loads(os.environ["RENDER_SYNC_ENV_JSON"])
if not isinstance(vals, dict) or not vals:
    sys.stderr.write("ERROR: RENDER_SYNC_ENV_JSON must be a non-empty object.\n")
    raise SystemExit(1)
for key, value in vals.items():
    if not key:
        sys.stderr.write("ERROR: RENDER_SYNC_ENV_JSON has an empty key.\n")
        raise SystemExit(1)
    print(f"{key}={value}")
'
  )
elif [ "$#" -gt 0 ]; then
  pairs=("$@")
else
  echo "ERROR: pass KEY=VALUE pairs or set RENDER_SYNC_ENV_JSON." >&2
  exit 1
fi

api_root="https://api.render.com/v1"

render_api() {
  local method="$1" path="$2"
  shift 2

  local response status body
  response="$(
    curl -sS -X "$method" \
      -H "Authorization: Bearer ${RENDER_API_KEY}" \
      -H "Accept: application/json" \
      -w $'\n%{http_code}' \
      "$@" \
      "${api_root}${path}"
  )"
  status="${response##*$'\n'}"
  body="${response%$'\n'*}"

  if [ "$status" -lt 200 ] || [ "$status" -ge 300 ]; then
    {
      echo "ERROR: Render API ${method} ${path} returned HTTP ${status}."
      case "$status" in
        401) echo "       RENDER_API_KEY was rejected — it is invalid, expired, or revoked." ;;
        403) echo "       RENDER_API_KEY cannot reach this resource — wrong Render workspace?" ;;
        404) echo "       Render has no such resource." ;;
        429) echo "       Rate limited by the Render API." ;;
      esac
      echo "       Response: ${body}"
    } >&2
    return 1
  fi

  printf '%s' "$body"
}

services="$(
  render_api GET "/services" -G \
    --data-urlencode "name=${SERVICE_NAME}" \
    --data-urlencode "limit=100"
)"

service_id="$(
  printf '%s' "$services" | python3 -c '
import json
import sys

wanted = sys.argv[1]
payload = json.load(sys.stdin)
rows = payload if isinstance(payload, list) else payload.get("items", payload.get("data", []))

seen = []
for row in rows:
    service = row.get("service", row)
    name = service.get("name")
    seen.append(str(name))
    if name == wanted:
        print(service["id"])
        raise SystemExit(0)

matched = ", ".join(seen) if seen else "(none)"
sys.stderr.write(
    "ERROR: Render has no service named " + repr(wanted) + ".\n"
    "       Services matching that name filter: " + matched + ".\n"
)
raise SystemExit(1)
' "$SERVICE_NAME"
)"

echo "Syncing env vars on ${SERVICE_NAME} (${service_id})"

for pair in "${pairs[@]}"; do
  key="${pair%%=*}"
  value="${pair#*=}"
  if [ "$key" = "$pair" ] || [ -z "$key" ]; then
    echo "ERROR: expected KEY=VALUE, got: $pair" >&2
    exit 1
  fi

  body="$(python3 -c 'import json, sys; print(json.dumps({"value": sys.argv[1]}))' "$value")"
  render_api PUT "/services/${service_id}/env-vars/${key}" \
    -H "Content-Type: application/json" \
    -d "$body" >/dev/null
  echo "  ${key}"
done
