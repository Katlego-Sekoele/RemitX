#!/usr/bin/env bash
# Trigger a Render deploy for $SERVICE_NAME and wait for it to finish.
#
# Auto-deploy is off on every Render service (Terraform sets
# auto_deploy_trigger = "off"), so this is the only rollout path after
# CI + terraform + migrate.
#
# Knobs (all optional):
#   RENDER_DEPLOY_WAIT              "false" to trigger and exit (default true)
#   RENDER_DEPLOY_TIMEOUT_SECONDS   give up waiting after this long (1800)
#   RENDER_DEPLOY_POLL_SECONDS      seconds between status polls (10)
#   RENDER_DEPLOY_MAX_POLL_ERRORS   consecutive API errors tolerated (5)
set -euo pipefail

: "${RENDER_API_KEY:?RENDER_API_KEY is not set. Add it to the GitHub environment for this deploy.}"
: "${SERVICE_NAME:?SERVICE_NAME is not set.}"

wait_for_deploy="${RENDER_DEPLOY_WAIT:-true}"
timeout_seconds="${RENDER_DEPLOY_TIMEOUT_SECONDS:-1800}"
poll_seconds="${RENDER_DEPLOY_POLL_SECONDS:-10}"
max_poll_errors="${RENDER_DEPLOY_MAX_POLL_ERRORS:-5}"

api_root="https://api.render.com/v1"

# curl exits 0 on 4xx/5xx, so every call has to check the status itself.
# Without this an error body parses as "no services matched", which is how a
# revoked API key masquerades as a missing service — and an unchecked POST
# lets Render reject the deploy while the job still reports success.
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

# The name filter is a substring match, so re-filter for an exact name.
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
    "       Terraform owns these services. Check that the `terraform` job in\n"
    "       this run applied infra/envs/<env> successfully — a fresh\n"
    "       environment has no services until it does.\n"
)
raise SystemExit(1)
' "$SERVICE_NAME"
)"

echo "Deploying ${SERVICE_NAME} (${service_id})"

deploy="$(
  render_api POST "/services/${service_id}/deploys" \
    -H "Content-Type: application/json" \
    -d '{"clearCache":"do_not_clear"}'
)"

deploy_id="$(
  printf '%s' "$deploy" | python3 -c 'import json, sys; print(json.load(sys.stdin)["id"])'
)"

echo "Triggered deploy ${deploy_id}"

if [ "$wait_for_deploy" != "true" ]; then
  echo "RENDER_DEPLOY_WAIT=${wait_for_deploy}; not waiting for ${deploy_id} to finish."
  exit 0
fi

# Statuses: created, queued, build_in_progress, pre_deploy_in_progress,
# update_in_progress, live, build_failed, pre_deploy_failed, update_failed,
# canceled, deactivated. Only `live` is success.
deadline=$(( SECONDS + timeout_seconds ))
consecutive_errors=0
last_status=""

while :; do
  if deploy_json="$(render_api GET "/services/${service_id}/deploys/${deploy_id}")"; then
    consecutive_errors=0
    status="$(
      printf '%s' "$deploy_json" \
        | python3 -c 'import json, sys; print(json.load(sys.stdin).get("status", ""))'
    )"

    if [ "$status" != "$last_status" ]; then
      echo "  ${SERVICE_NAME}: ${status}"
      last_status="$status"
    fi

    case "$status" in
      live)
        echo "Deploy ${deploy_id} for ${SERVICE_NAME} is live."
        exit 0
        ;;
      build_failed | pre_deploy_failed | update_failed | canceled | deactivated)
        {
          echo "ERROR: deploy ${deploy_id} for ${SERVICE_NAME} finished as '${status}'."
          echo "       Read the deploy log for service ${service_id} in the Render dashboard."
        } >&2
        exit 1
        ;;
    esac
  else
    consecutive_errors=$(( consecutive_errors + 1 ))
    echo "WARNING: could not read deploy ${deploy_id} (${consecutive_errors}/${max_poll_errors})." >&2
    if [ "$consecutive_errors" -ge "$max_poll_errors" ]; then
      echo "ERROR: giving up after ${consecutive_errors} consecutive Render API errors." >&2
      exit 1
    fi
  fi

  if [ "$SECONDS" -ge "$deadline" ]; then
    {
      echo "ERROR: deploy ${deploy_id} for ${SERVICE_NAME} did not finish within ${timeout_seconds}s."
      echo "       Last status: '${last_status:-unknown}'. It may still be running on Render."
    } >&2
    exit 1
  fi

  sleep "$poll_seconds"
done
