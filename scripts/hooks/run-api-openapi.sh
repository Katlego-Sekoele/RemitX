#!/usr/bin/env bash
# Regenerate frontend/openapi.json from the API and stage it, so the client the
# frontend generates from it never lags the routes being committed.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root/api"

if [[ -x .venv/bin/python ]]; then
  python=.venv/bin/python
elif python3 -c "import remitx_api" >/dev/null 2>&1; then
  python=python3
else
  echo "ERROR: API environment not found. Run: cd api && pip install -e '.[dev]'" >&2
  exit 1
fi

"$python" scripts/export_openapi.py

cd "$root"
git add frontend/openapi.json
