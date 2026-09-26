#!/usr/bin/env bash
# Runs the load test end to end on a throwaway stack, then deletes the stack.
#
#   make loadtest        (or tools/loadtest/run.sh)
#
# Builds the images, seeds a fresh Postgres through the seeder, starts the API
# and worker, and runs Locust headless. The report lands in
# tools/loadtest/results/<timestamp>/. Every container, network and volume the
# stack created is deleted at the end, whether the run passed, failed or was
# interrupted. KEEP_STACK=1 leaves it running instead; `make loadtest-down`
# deletes it later.
#
# Knobs (all optional): LOADTEST_STEPS, LOADTEST_STEP_SECONDS,
# LOADTEST_SPAWN_RATE, LOADTEST_BURN_P50_S, LOADTEST_BURN_P95_S,
# LOADTEST_BURN_FAILURE_RATE, LOADTEST_CELERY_CONCURRENCY,
# LOADTEST_API_CPUS, LOADTEST_API_MEMORY, LOADTEST_WORKER_CPUS,
# LOADTEST_WORKER_MEMORY. See README.md.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
compose=(docker compose -f "$here/docker-compose.yml" --profile tools)

results="$here/results/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$results"
export LOADTEST_RESULTS_DIR="$results"
LOADTEST_UID="$(id -u)"
LOADTEST_GID="$(id -g)"
export LOADTEST_UID LOADTEST_GID

teardown() {
  "${compose[@]}" logs --no-color api worker >"$results/services.log" 2>&1 || true
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

echo "==> Running Locust (starts the API and worker first)"
"${compose[@]}" run --rm locust

echo "==> Report: $results/report.html"
