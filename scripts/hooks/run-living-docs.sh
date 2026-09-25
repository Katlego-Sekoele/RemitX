#!/usr/bin/env bash
# Check every reference the docs under docs/ make still resolves against the
# API spec, the database schema and the components (frontend/living-docs).
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root/frontend"

if [[ ! -d node_modules ]]; then
  echo "ERROR: frontend/node_modules missing. Run: cd frontend && npm ci" >&2
  exit 1
fi

npm run --silent docs:check
