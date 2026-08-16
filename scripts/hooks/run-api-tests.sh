#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root/api"

if [[ -x .venv/bin/pytest ]]; then
  .venv/bin/pytest
elif python3 -m pytest --version >/dev/null 2>&1; then
  python3 -m pytest
else
  echo "ERROR: pytest not found. Run: cd api && pip install -e '.[dev]'" >&2
  exit 1
fi
