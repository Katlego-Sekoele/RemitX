#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ ! -f "$root/contracts/package.json" ]]; then
  exit 0
fi

cd "$root/contracts"

if [[ ! -d node_modules ]]; then
  echo "ERROR: contracts/node_modules missing. Run: cd contracts && npm ci" >&2
  exit 1
fi

npm test
