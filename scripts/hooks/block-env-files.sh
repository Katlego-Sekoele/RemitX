#!/usr/bin/env bash
set -euo pipefail

blocked=()

while IFS= read -r file; do
  base="$(basename "$file")"
  # `.env` and per-target variants such as `.env.qa` hold real credentials;
  # `.env.example` and `.env.qa.example` are the committed templates.
  if [[ "$base" == ".env" || ( "$base" == .env.* && "$base" != *.example ) ]]; then
    blocked+=("$file")
  fi
done < <(git diff --cached --name-only --diff-filter=ACM)

if ((${#blocked[@]} > 0)); then
  echo "ERROR: Refusing to commit secrets file(s):" >&2
  printf '  - %s\n' "${blocked[@]}" >&2
  echo "Use .env.example (or .env.<target>.example) for templates; keep real values in the gitignored file." >&2
  exit 1
fi
