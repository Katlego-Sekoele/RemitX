#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ ! -f "$root/frontend/package.json" ]]; then
  exit 0
fi

cd "$root/frontend"

if [[ ! -d node_modules ]]; then
  echo "ERROR: frontend/node_modules missing. Run: cd frontend && npm ci" >&2
  exit 1
fi

staged=()
while IFS= read -r file; do
  staged+=("$file")
done < <(git diff --cached --name-only --diff-filter=ACM | grep '^frontend/' || true)

if ((${#staged[@]} > 0)); then
  rel=()
  for file in "${staged[@]}"; do
    rel+=("${file#frontend/}")
  done
  npx prettier --write "${rel[@]}"
  cd "$root"
  for file in "${staged[@]}"; do
    git add "$file"
  done
  cd "$root/frontend"
fi

npm run typecheck
