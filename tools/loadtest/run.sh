#!/usr/bin/env bash
# Runs the load test end to end on a throwaway stack, then deletes the stack.
#
#   make loadtest        (or tools/loadtest/run.sh)
#   LOADTEST_PROFILE=default make loadtest
#   LOADTEST_PROFILE=compute-sweep make loadtest
#
# Loads a profile from tools/loadtest/profiles/ (population, Locust shape,
# simulated burn, optional compute sweep of API/worker/Postgres), builds the
# stack, seeds a fresh Postgres once, then for each compute step recreates
# Postgres + API + worker, runs Locust headless, and writes stats under
# compute/<name>/. Finally it builds summary.json + report.canvas.tsx and
# deletes the stack.
# KEEP_STACK=1 leaves the stack up; `make loadtest-down` deletes it later.
#
# Edit profiles/*.json to change the run. Operational only: LOADTEST_PROFILE
# (default default), KEEP_STACK.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
compose=(docker compose -f "$here/docker-compose.yml" --profile tools)

results="$here/results/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$results"
export LOADTEST_RESULTS_DIR="$results"
LOADTEST_UID="$(id -u)"
LOADTEST_GID="$(id -g)"
export LOADTEST_UID LOADTEST_GID

profile_name="${LOADTEST_PROFILE:-default}"
seed_scenario="$results/seed-scenario.json"
profile_env="$results/profile.env"

# Prefer the seeder venv (has remitx_seeder for seed validation); fall back to
# whatever python3 is on PATH with tools/seeder on PYTHONPATH.
if [[ -x "$here/../seeder/.venv/bin/python" ]]; then
  profile_python=("$here/../seeder/.venv/bin/python")
else
  profile_python=(env PYTHONPATH="$here/../seeder${PYTHONPATH:+:$PYTHONPATH}" python3)
fi

echo "==> Profile: $profile_name"
"${profile_python[@]}" "$here/loadtest_profile.py" apply "$profile_name" \
  --write-seed "$seed_scenario" \
  --exports >"$profile_env"
# shellcheck disable=SC1090
set -a && source "$profile_env" && set +a
export LOADTEST_SEED_SCENARIO="$seed_scenario"
cp "$here/profiles/${profile_name}.json" "$results/profile.json"

compute_json="$results/compute-steps.json"
"${profile_python[@]}" "$here/loadtest_profile.py" compute-steps "$profile_name" \
  >"$compute_json"

teardown() {
  if [[ "${KEEP_STACK:-0}" == "1" ]]; then
    echo "==> KEEP_STACK=1: the stack is still up. Delete it with: make loadtest-down"
    return
  fi
  echo "==> Deleting the stack: containers, network and volumes"
  "${compose[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap teardown EXIT

echo "==> Building images"
"${compose[@]}" build

echo "==> Seeding a fresh database (log: ${results#"$here"/}/seed.log)"
if ! "${compose[@]}" run --rm -T seeder >"$results/seed.log" 2>&1; then
  echo "Seeding failed; the end of seed.log:" >&2
  tail -n 25 "$results/seed.log" >&2
  exit 1
fi
tail -n 1 "$results/seed.log"

# Seed already brought up migrate + minio-setup (one-shots). Only wait on
# long-running shared services here; Postgres is recreated per compute step
# but keeps its volume so the seeded data survives.
echo "==> Starting shared infrastructure (redis, minio)"
"${compose[@]}" up -d --wait redis minio

compute_names=()
while IFS= read -r compute_name; do
  [[ -n "$compute_name" ]] && compute_names+=("$compute_name")
done < <(
  "${profile_python[@]}" -c "
import json, sys
for step in json.load(open(sys.argv[1])):
    print(step['name'])
" "$compute_json"
)

for compute_name in "${compute_names[@]}"; do
  echo "==> Compute: $compute_name"
  step_dir="$results/compute/$compute_name"
  mkdir -p "$step_dir"

  "${profile_python[@]}" "$here/loadtest_profile.py" exports-for \
    "$profile_name" "$compute_name" >"$step_dir/profile.env"
  # shellcheck disable=SC1090
  set -a && source "$step_dir/profile.env" && set +a

  echo "==> Recreating postgres + API + worker ($compute_name: API ${LOADTEST_API_CPUS} CPU / worker ${LOADTEST_WORKER_CPUS} CPU / postgres ${LOADTEST_POSTGRES_CPUS} CPU)"
  "${compose[@]}" up -d --force-recreate --wait postgres
  "${compose[@]}" up -d --force-recreate --wait api worker

  echo "==> Running Locust → compute/$compute_name/"
  LOADTEST_RESULTS_DIR="$step_dir" "${compose[@]}" run --rm locust
  "${compose[@]}" logs --no-color api worker postgres \
    >"$step_dir/services.log" 2>&1 || true
done

echo "==> Writing summary.json, report.canvas.tsx, performance-report.html"
"${profile_python[@]}" "$here/to_canvas.py" "$results"

echo "==> Report: $results/performance-report.html"
echo "==> Summary: $results/summary.json"
