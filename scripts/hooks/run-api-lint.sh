#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

staged=()
while IFS= read -r file; do
  staged+=("$file")
done < <(git diff --cached --name-only --diff-filter=ACM | grep '^api/' || true)

if ((${#staged[@]} == 0)); then
  exit 0
fi

py_staged=()
for file in "${staged[@]}"; do
  if [[ "$file" == *.py ]]; then
    py_staged+=("$file")
  fi
done

if [[ -x api/.venv/bin/ruff ]]; then
  ruff=(api/.venv/bin/ruff)
elif command -v ruff >/dev/null 2>&1; then
  ruff=(ruff)
elif python3 -m ruff --version >/dev/null 2>&1; then
  ruff=(python3 -m ruff)
else
  echo "ERROR: ruff not found. Run: cd api && pip install -e '.[dev]'" >&2
  exit 1
fi

if ((${#py_staged[@]} > 0)); then
  "${ruff[@]}" check --fix --config api/pyproject.toml "${py_staged[@]}"
  "${ruff[@]}" format --config api/pyproject.toml "${py_staged[@]}"
fi

for file in "${staged[@]}"; do
  git add "$file"
done
