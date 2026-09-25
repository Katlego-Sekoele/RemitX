#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

if ! python3 -m pre_commit --version >/dev/null 2>&1; then
  echo "Installing pre-commit..."
  python3 -m pip install --user pre-commit
fi

python3 -m pre_commit install
echo "Git pre-commit hooks installed."
echo "  - gitleaks, block-env-files"
echo "  - api: ruff (auto-fix + format), pytest"
echo "  - frontend: prettier (auto-fix all), lint (typecheck + format:check)"
echo "  - living docs: every reference under docs/ resolves (npm run docs:check)"
echo ""
echo "Dev setup:"
echo "  brew install gitleaks    # if secret scan hook cannot find a binary"
echo "  cd api && pip install -e '.[dev]'"
echo "  cd frontend && npm ci"
echo ""
echo "Run manually: python3 -m pre_commit run --all-files"
