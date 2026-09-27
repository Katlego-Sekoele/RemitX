# Load test

Load-tests the API with [Locust](https://locust.io) on a throwaway copy of the
stack, without calling Clerk, the exchange-rate API or the XRPL testnet.

```bash
make loadtest
LOADTEST_PROFILE=compute-sweep make loadtest   # API 0.1 then 1.0 CPU
```

It needs Docker with enough RAM for Neon-sized Postgres (default profile:
~8 GB for Postgres plus the API/worker) and a Python that can import the
seeder (the seeder venv from `make seeder-install` is preferred). A default
run takes about 15 minutes of Locust after seeding; a compute sweep multiplies
the Locust phase by the number of compute steps (one shared seed).

Each run writes to `tools/loadtest/results/<timestamp>/`:

| Path | Committed? |
|---|---|
| `profile.json` | yes |
| `summary.json` | yes |
| `report.canvas.tsx` | yes (Cursor canvas) |
| `performance-report.html` | yes (open in a browser) |
| `compute/<name>/stats*`, `report.html`, `services.log` | no (gitignored) |
| `seed.log` | no |

## Profiles

Everything about a run lives in one JSON file under
[`profiles/`](profiles/): how many people to seed, the Locust step shape, the
simulated XRPL burn, API/worker limits, and an optional **compute** sweep.

```bash
make loadtest                          # profiles/default.json (single compute)
LOADTEST_PROFILE=compute-sweep make loadtest
```

Edit the profile (or copy it to a new name under `profiles/`) instead of
passing env knobs. `run.sh` validates the file, writes the nested `seed`
block for the seeder, and feeds the rest into the stack.

| Section | What it sets |
|---|---|
| `seed` | Seeder scenario (senders, KYC/money rates, …) |
| `locust` | `steps`, `step_seconds`, `spawn_rate` |
| `burn` | Simulated XRPL delay (`p50_s`, `p95_s`) and `failure_rate` |
| `api` / `worker` / `postgres` | Single-run limits when `compute` is omitted. With a sweep: top-level `api` and `worker` are forbidden; top-level `postgres` holds only `max_connections` (shared). |
| `compute` | Optional list of full steps `{ name, api, worker, postgres }`. Seed once; recreate Postgres + API + worker per step; same Locust user ramp. Order small→large so the starved case sees the cleaner DB first. |
| `database_pool` | SQLAlchemy QueuePool per process (fixed for the run). |

## What a run does

1. Loads the profile, builds three images: the production API image (migrations,
   API, worker), the seeder, and Locust.
2. Starts a fresh Postgres, Redis and MinIO on their own volumes, and migrates.
3. Seeds through the seeder's `loadtest` target with the profile's `seed`
   block: verified, funded senders with beneficiaries, created by the
   backend's own code.
4. Runs `prepare.py`: stores exchange rates that never expire, generates a
   throwaway key pair for signing session tokens, and lists the people Locust
   acts as.
5. For each `compute` step (or one implicit `default` step): recreates
   Postgres, API and worker with that step’s CPU/memory (data volume kept),
   then runs Locust headless. Stats land in `compute/<name>/`.
6. Writes `summary.json`, `report.canvas.tsx`, and `performance-report.html`.
7. Deletes every container, network and volume it created, even if the run
   failed or you pressed Ctrl-C. `KEEP_STACK=1 make loadtest` keeps them;
   `make loadtest-down` deletes them afterwards.

Later compute steps see remittances left by earlier ones. Prefer ordering
`compute` from smaller to larger tiers so the starved case runs first.

## No calls to external partners

| Partner | How the load test avoids it |
|---|---|
| Clerk | The API verifies session tokens with `CLERK_JWT_KEY`, the throwaway public key, and Locust signs its own tokens with the private half. There is no secret key, so the API never calls Clerk. |
| Exchange-rate API | Rates are stored with a far-future expiry, and no API key is set. |
| XRPL testnet | The worker's one XRPL call is simulated (`fake_xrpl_worker.py`) with a delay calibrated on QA. No wallet is configured. |

The stack's Docker network is also `internal`: nothing in it can reach the
internet, so a partner call that slipped through would fail, not leave.

## Performance report

`to_canvas.py` builds the graded deliverable from Locust CSVs into both
`report.canvas.tsx` (Cursor canvas) and a self-contained
`performance-report.html` (open in any browser). It covers:

- API response times (HTTP-only; SETTLE excluded)
- Requests processed per second
- Message-queue throughput (`SETTLE` / `end to end` settlements/s)
- RLUSD transaction processing time (calibrated `burn` + in-run `chain + confirm`)
- Transaction success and failure rates
- Behaviour under concurrent use (curves vs Locust user steps × compute)
- A short bottleneck explanation

Regenerate without re-running Locust:

```bash
make loadtest-canvas RESULTS=tools/loadtest/results/<timestamp>
```

Open `performance-report.html` in a browser. Cursor live-renders
`report.canvas.tsx` from its managed `canvases/` folder — copy or symlink
there if you want the live view; the in-repo files are the source of truth.

## Reading Locust CSVs

- **Requests**: response times (median to 99th percentile), requests per
  second and failures, per endpoint and over time as the load steps up.
- **SETTLE rows**: settlement timed from the API's own timestamps.
  `queue wait` is sent until the worker picked the burn up, `chain + confirm`
  the burn plus the confirm task, `end to end` both. The request rate of
  `end to end` is settlements per second: the queue's throughput.
- Locust **Aggregated** mixes SETTLE into medians — prefer the canvas / HTTP-only figures.

## Calibrating the simulated XRPL burn

Run [`qa_xrpl_timings.sql`](qa_xrpl_timings.sql) in the Neon SQL editor on the
QA branch. It measures real testnet settlements, skips the seeder's simulated
ones, and drops outliers such as the worker-wake bug's multi-hour waits
(anything outside Tukey's far-out fences). Put its `burn_p50_s` and
`burn_p95_s` in the profile's `burn` section:

```json
"burn": { "p50_s": 4.2, "p95_s": 7.9, "failure_rate": 0 }
```

Report the query's real testnet figures as the RLUSD transaction processing
time; the load test's own SETTLE rows show how the queue behaves under load.

## Files

| File | Purpose |
|---|---|
| `run.sh` | The whole run, called by `make loadtest` |
| `profiles/*.json` | Run profiles (population + load + limits + optional compute) |
| `loadtest_profile.py` | Load, validate and apply a profile; list compute steps |
| `loadtest_summary.py` | Parse Locust CSVs into a structured summary |
| `to_canvas.py` | Write `summary.json` + canvas + `performance-report.html` |
| `docker-compose.yml` | The throwaway stack |
| `loadtest.env` | Stack credentials for the seeder's `loadtest` target. Nothing secret |
| `prepare.py` | Rates, signing keys and the people list, after seeding |
| `fake_xrpl_worker.py` | The real worker with a simulated XRPL burn |
| `locustfile.py` | What the simulated people do, and the stepped load |
| `qa_xrpl_timings.sql` | Real settlement timings from QA, outliers removed |
