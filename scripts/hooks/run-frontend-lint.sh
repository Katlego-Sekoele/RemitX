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

# Format the whole frontend tree so CI (format:check on all files) stays in sync,
# not only paths staged for this commit.
npm run format

cd "$root"
while IFS= read -r file; do
  [[ -n "$file" ]] && git add "$file"
# Deleted paths are already staged as deletions; `git add` would fail on them.
done < <(git diff --name-only --diff-filter=d HEAD -- frontend/ || true)

cd "$root/frontend"
npm run lint
