# The QA seeder writes through the backend's own code, not SQL

RemitX's most important rules live in Python rather than in the schema: a
balance equals its confirmed ledger rows, a remittance is seven legs that
settle together, the KYC state machine and its history, SA ID check digits,
fee rounding. A seeder inserting rows directly would have to re-implement
those rules and would drift silently as they change, producing states the app
could never reach. So the seeder (`tools/seeder`) calls the same controllers,
services and worker tasks a request does, in-process. A rule change is then
picked up automatically, or breaks the seeder's CI job in the PR that made it.
Writes no product flow can make yet are confined to `tools/seeder/remitx_seeder/direct.py`
and checked by `verify` after every run.

## Considered options

- **Direct inserts, validated against the live schema.** Fast and able to
  backdate anything, but the schema carries only a fraction of the rules.
- **Calling the HTTP API.** The highest fidelity, but every synthetic person
  needs a Clerk session, free-tier cold starts make it slow, and nothing can be
  backdated. Kept for the live tail (a few real end-to-end settlements).

## Consequences

- The seeder is Python and imports `remitx_api` (as `remitx_worker` does;
  `remitx_api` never imports it).
- History is produced by moving the process clock (`time-machine`) rather than
  by rewriting timestamps, and the exchange-rate provider became replaceable
  (`use_rate_provider`) so replayed days get rates for those days.
- It is a local tool, never deployed: QA is seeded by a developer on purpose,
  never by CI or a service. It has its own per-target env file
  (`tools/seeder/.env.qa`), a deliberate exception to the single root `.env`.
