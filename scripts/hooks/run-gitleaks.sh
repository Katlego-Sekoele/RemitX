#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

find_gitleaks() {
  if command -v gitleaks >/dev/null 2>&1; then
    command -v gitleaks
    return
  fi

  find "${HOME}/.cache/pre-commit" -path '*/bin/gitleaks' -type f 2>/dev/null | head -1
}

gitleaks="$(find_gitleaks)"
if [[ -z "${gitleaks}" ]]; then
  echo "ERROR: gitleaks not found. Run: ./scripts/setup-hooks.sh" >&2
  exit 1
fi

staged=()
while IFS= read -r file; do
  if [[ -f "$file" ]] && ! git check-ignore -q "$file"; then
    staged+=("$file")
  fi
done < <(git diff --cached --name-only --diff-filter=ACM)

if ((${#staged[@]} == 0)); then
  exit 0
fi

"${gitleaks}" git --pre-commit --staged --redact --verbose --config .gitleaks.toml .

for file in "${staged[@]}"; do
  "${gitleaks}" dir "$file" --redact --verbose --config .gitleaks.toml
done
