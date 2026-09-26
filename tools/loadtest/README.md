# Load test

Load-tests the API with [Locust](https://locust.io) on a throwaway copy of the
stack, without calling Clerk, the exchange-rate API or the XRPL testnet.

```bash
make loadtest
```

It needs only Docker (give it about 4 GB of memory). A default run takes about
15 minutes: a few to build and seed, then 10 of load. Each run writes to
`tools/loadtest/results/<timestamp>/`:
Locust's `report.html`, its `stats*.csv`, plus `seed.log` and `services.log`
(the API's and worker's logs) for digging into failures.

## What a run does

1. Builds three images: the production API image (used for migrations, the API
   and the worker), the seeder, and Locust.
2. Starts a fresh Postgres, Redis and MinIO on their own volumes, and migrates.
3. Seeds through the seeder's `loadtest` target and scenario: a few hundred
   database-only people, verified, funded and with beneficiaries, created by
   the backend's own code.
4. Runs `prepare.py`: stores exchange rates that never expire, generates a
   throwaway key pair for signing session tokens, and lists the people Locust
   acts as.
5. Starts the API and worker, then runs Locust headless with a stepped load:
   10, 25, 50, 100 and 200 users, 2 minutes each.
6. Deletes every container, network and volume it created, even if the run
   failed or you pressed Ctrl-C. `KEEP_STACK=1 make loadtest` keeps them;
   `make loadtest-down` deletes them afterwards.

## No calls to external partners

| Partner | How the load test avoids it |
|---|---|
| Clerk | The API verifies session tokens with `CLERK_JWT_KEY`, the throwaway public key, and Locust signs its own tokens with the private half. There is no secret key, so the API never calls Clerk. |
| Exchange-rate API | Rates are stored with a far-future expiry, and no API key is set. |
| XRPL testnet | The worker's one XRPL call is simulated (`fake_xrpl_worker.py`) with a delay calibrated on QA. No wallet is configured. |

The stack's Docker network is also `internal`: nothing in it can reach the
internet, so a partner call that slipped through would fail, not leave.

## Reading the report

- **Requests**: response times (median to 99th percentile), requests per
  second and failures, per endpoint and over time as the load steps up.
- **SETTLE rows**: settlement timed from the API's own timestamps.
  `queue wait` is sent until the worker picked the burn up, `chain + confirm`
  the burn plus the confirm task, `end to end` both. The request rate of
  `end to end` is settlements per second: the queue's throughput.

## Calibrating the simulated XRPL burn

Run [`qa_xrpl_timings.sql`](qa_xrpl_timings.sql) in the Neon SQL editor on the
QA branch. It measures real testnet settlements, skips the seeder's simulated
ones, and drops outliers such as the worker-wake bug's multi-hour waits
(anything outside Tukey's far-out fences). Its `burn_p50_s` and `burn_p95_s`
set the simulated delay:

```bash
LOADTEST_BURN_P50_S=4.2 LOADTEST_BURN_P95_S=7.9 make loadtest
```

Report the query's real testnet figures as the RLUSD transaction processing
time; the load test's own SETTLE rows show how the queue behaves under load.

## Settings

All optional, as environment variables to `make loadtest`:

| Variable | Default | What it sets |
|---|---|---|
| `LOADTEST_STEPS` | `10,25,50,100,200` | User counts, in order |
| `LOADTEST_STEP_SECONDS` | `120` | How long each step lasts |
| `LOADTEST_SPAWN_RATE` | `10` | Users started per second |
| `LOADTEST_BURN_P50_S`, `LOADTEST_BURN_P95_S` | `4.0`, `8.0` | Simulated burn delay (see above) |
| `LOADTEST_BURN_FAILURE_RATE` | `0` | Share of burns that fail |
| `LOADTEST_CELERY_CONCURRENCY` | `2` | Worker processes, as on Render |
| `LOADTEST_API_CPUS`, `LOADTEST_WORKER_CPUS` | `1` | CPU limit; `0.1` matches a Render free instance |
| `LOADTEST_API_MEMORY`, `LOADTEST_WORKER_MEMORY` | `512m` | Memory limit of a Render free instance |

## Files

| File | Purpose |
|---|---|
| `run.sh` | The whole run, called by `make loadtest` |
| `docker-compose.yml` | The throwaway stack |
| `loadtest.env` | Its configuration, and the seeder's `loadtest` target. Nothing secret |
| `prepare.py` | Rates, signing keys and the people list, after seeding |
| `fake_xrpl_worker.py` | The real worker with a simulated XRPL burn |
| `locustfile.py` | What the simulated people do, and the stepped load |
| `qa_xrpl_timings.sql` | Real settlement timings from QA, outliers removed |
