#!/usr/bin/env bash
# Trigger a Render deploy for $SERVICE_NAME. Auto-deploy is off so this is
# the only rollout path after CI + migrate.
set -euo pipefail

if [ -z "${RENDER_API_KEY:-}" ]; then
  echo "ERROR: RENDER_API_KEY is not set." >&2
  exit 1
fi
if [ -z "${SERVICE_NAME:-}" ]; then
  echo "ERROR: SERVICE_NAME is not set." >&2
  exit 1
fi

auth=( -H "Authorization: Bearer ${RENDER_API_KEY}" -H "Accept: application/json" )

service_id="$(
  curl -sS "${auth[@]}" \
    "https://api.render.com/v1/services?name=${SERVICE_NAME}&limit=20" \
    | python3 -c "
import json, sys
payload = json.load(sys.stdin)
rows = payload if isinstance(payload, list) else payload.get('items', payload.get('data', []))
wanted = sys.argv[1]
for row in rows:
    service = row.get('service', row)
    if service.get('name') == wanted:
        print(service['id'])
        raise SystemExit(0)
raise SystemExit(f'service {wanted!r} not found')
" "${SERVICE_NAME}"
)"

echo "Deploying ${SERVICE_NAME} (${service_id})"

curl -sS -X POST "${auth[@]}" \
  -H "Content-Type: application/json" \
  -d '{"clearCache":"do_not_clear"}' \
  "https://api.render.com/v1/services/${service_id}/deploys"
echo
