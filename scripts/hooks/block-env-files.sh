#!/usr/bin/env bash
set -euo pipefail

blocked=()

while IFS= read -r file; do
  base="$(basename "$file")"
  if [[ "$base" == ".env" ]]; then
    blocked+=("$file")
  fi
done < <(git diff --cached --name-only --diff-filter=ACM)

if ((${#blocked[@]} > 0)); then
  echo "ERROR: Refusing to commit secrets file(s):" >&2
  printf '  - %s\n' "${blocked[@]}" >&2
  echo "Use .env.example for templates; keep real values in .env (gitignored)." >&2
  exit 1
fi
