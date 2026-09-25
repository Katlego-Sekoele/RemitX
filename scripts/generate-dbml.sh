#!/usr/bin/env bash
# Regenerate docs/database/schema.dbml, the Postgres schema the living docs
# (frontend/living-docs) read, with the dbdiagram CLI's db2dbml.
#
#   scripts/generate-dbml.sh           # rewrite docs/database/schema.dbml
#   scripts/generate-dbml.sh --check   # exit 1 if it is stale (CI does this)
#
# The schema comes from a throwaway database migrated to head, never from one
# people use: the file must describe what the migrations build, not what a dev
# database has drifted into. That takes a Postgres server this may create a
# database on — DBML_DATABASE_URL, else DATABASE_URL from the repo-root .env
# (the compose Postgres works) — plus the API environment for Alembic, and
# Node >= 22.18 for the CLI and the canonical ordering step.
set -euo pipefail

check=false
case "${1:-}" in
  --check) check=true ;;
  "") ;;
  *)
    echo "usage: $0 [--check]" >&2
    exit 2
    ;;
esac

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target="$root/docs/database/schema.dbml"

if [[ -x "$root/api/.venv/bin/python" ]]; then
  python="$root/api/.venv/bin/python"
elif python3 -c "import alembic, remitx_api" >/dev/null 2>&1; then
  python=python3
else
  echo "ERROR: API environment not found. Run: cd api && pip install -e '.[dev]'" >&2
  exit 1
fi

if [[ ! -d "$root/frontend/node_modules/@dbml/core" ]]; then
  echo "ERROR: frontend/node_modules missing. Run: cd frontend && npm ci" >&2
  exit 1
fi

work="$(mktemp -d)"
db_url="$("$python" "$root/api/scripts/throwaway_database.py" create)"
cleanup() {
  "$python" "$root/api/scripts/throwaway_database.py" drop "$db_url" || true
  rm -rf "$work"
}
trap cleanup EXIT

# An empty PLATFORM_WALLET_ADDRESS keeps the treasury-funding migration from
# reading the XRPL testnet: it seeds a row, which is no part of the schema.
(cd "$root/api" && PLATFORM_WALLET_ADDRESS="" "$python" -m alembic -x url="$db_url" upgrade head) 2>"$work/alembic.log" || {
  cat "$work/alembic.log" >&2
  exit 1
}

# db2dbml speaks libpq URLs, without SQLAlchemy's +driver suffix. Every @dbml
# package is pinned so that npx cannot float the CLI onto another parser; bump
# them together with @dbml/core in frontend/package.json.
pg_url="$(sed -E 's#^postgresql\+[a-z0-9]+://#postgresql://#' <<<"$db_url")"
(
  cd "$work"
  npx --yes \
    --package=@dbml/cli@10.2.0 \
    --package=@dbml/core@10.2.0 \
    --package=@dbml/connector@10.2.0 \
    --package=@dbml/parse@10.2.0 \
    -- db2dbml postgres "$pg_url" -o "$work/raw.dbml" >/dev/null 2>"$work/db2dbml.log"
)

# db2dbml reports a failed connection or query and still exits 0, so an output
# file is the only sign it worked.
if [[ ! -s "$work/raw.dbml" ]]; then
  echo "ERROR: db2dbml wrote no schema." >&2
  cat "$work/db2dbml.log" "$work/dbml-error.log" 2>/dev/null >&2 || true
  exit 1
fi

# db2dbml reads CHECK constraints (and a table's foreign keys) in whatever
# order Postgres returns them, which is not stable between runs. Sort them so
# the committed file only changes when the schema does.
(cd "$root/frontend" && node living-docs/cli.ts canonicalize-dbml "$work/raw.dbml") >"$work/schema.dbml"

if $check; then
  if ! diff -u "$target" "$work/schema.dbml" >"$work/schema.diff" 2>&1; then
    cat "$work/schema.diff" >&2
    echo >&2
    echo "ERROR: docs/database/schema.dbml is stale. Run: scripts/generate-dbml.sh" >&2
    exit 1
  fi
  exit 0
fi

mkdir -p "$(dirname "$target")"
if ! cmp -s "$work/schema.dbml" "$target"; then
  cp "$work/schema.dbml" "$target"
  echo "wrote docs/database/schema.dbml"
fi
