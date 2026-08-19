# Database migrations

Alembic owns the Postgres schema in **every** environment — local Docker, QA,
and production. SQLAlchemy never creates tables against Postgres; if a table is
not in `versions/`, it does not exist.

(Tests are the one exception: they run on a throwaway in-memory SQLite database
built by `create_all()`, enabled by `TestConfig.CREATE_ALL`. See
[../remitx_api/config.py](../remitx_api/config.py).)

## Naming standard

```
V<UTC yyyyMMdd_HHmm>__<snake_case_summary>.py
```

for example

```
V20260819_0040__create_integration_messages.py
V20260901_0930__add_transfers_status_index.py
```

The filename is set automatically by `file_template` in
[../alembic.ini](../alembic.ini), with `timezone = UTC`, so you never type it.
Timestamps rather than sequential numbers: with `qa` and `main` as
branch-per-environment, two branches adding a migration on the same day would
otherwise collide.

Note that the filename is for humans. Alembic's real ordering is the
`revision` / `down_revision` chain inside each file.

## Adding a migration

Edit the ORM models under [../remitx_api/models/orm/](../remitx_api/models/orm/)
first — they are the source of truth — then let Alembic diff them against the
current database:

```bash
cd api && source .venv/bin/activate
alembic revision --autogenerate -m "add transfers status index"
```

Autogenerate compares the models against a **live, already-migrated** database,
so start the local Postgres first:

```bash
docker compose -f docker-compose.dev.yml up -d postgres
cd api && alembic upgrade head        # bring it to the current head first
alembic revision --autogenerate -m "add transfers status index"
```

Bringing it to head first is not optional. Autogenerating against an empty
database diffs the entire ORM against nothing and emits `create_table` for
*every* table, which then fails on Postgres with `relation ... already exists`.

Use Postgres, not a scratch SQLite file. The dialects genuinely differ —
`sa.Uuid` is a native UUID on Postgres and `CHAR(32)` on SQLite, and CHECK
constraint reflection is not the same — so a SQLite-derived diff can encode the
wrong thing in a project whose whole point is eliminating drift.

**Always read the generated file before committing it.** Autogenerate is a
strong first draft, not gospel. It reliably detects tables, columns, indexes
and foreign keys. It is unreliable about:

- `CHECK` constraint *changes* on existing tables (new tables are fine)
- server default changes
- some column type alterations
- anything requiring data backfill, which it cannot infer at all

Then apply and lint:

```bash
alembic upgrade head
ruff check --fix alembic/ && ruff format alembic/
```

## Rules

1. **One logical change per migration.** A file that both creates a table and
   backfills it is two migrations.
2. **Never edit a migration that has been applied anywhere.** QA and production
   have already recorded it as run. Supersede it with a new one.
3. **Write a real `downgrade()`.** Autogenerate produces one for schema changes;
   if you hand-write a data migration, make the reverse explicit or raise
   `NotImplementedError` rather than leaving `pass`, which silently lies.
4. **Keep the ORM and the migration in step.** After applying, `alembic check`
   must report "No new upgrade operations detected". Anything else means the
   model and the schema have drifted. CI enforces this on every PR.
5. **Every migration must be safe against the app version already running.**
   Migrations are applied *before* the new image rolls out, and Container Apps
   does a rolling update, so the old code keeps serving traffic against the new
   schema for the duration. Additive changes are safe in a single release: new
   tables, new nullable columns, new indexes. Anything destructive or narrowing
   — dropping a column, renaming, adding `NOT NULL`, tightening a type — splits
   across two releases:

   **expand** (add the new shape, write to both) → deploy code that uses it →
   **contract** (drop the old shape) in a later migration.

   Never pair a rename with the code change that depends on it.

## Operational notes

- `alembic upgrade head` runs the whole chain in **one transaction**
  (`transaction_per_migration` is left at its default), so on Postgres a
  mid-chain failure rolls everything back — you can never land half-migrated.
- That also means `CREATE INDEX CONCURRENTLY` will not work as-is; it cannot
  run inside a transaction. It needs `transaction_per_migration = True` plus an
  autocommit block.
- Long DDL takes an `ACCESS EXCLUSIVE` lock. Set a `lock_timeout` in the
  migration so it queues behind a slow query instead of stalling the table.
- Two branches that each add a migration produce **two heads** on merge, and
  `alembic upgrade head` then fails with "Multiple head revisions are present".
  That failure is loud and safely blocks the deploy; resolve it with
  `alembic merge heads`.
- If a migration succeeds but `deploy-api` then fails, the new schema is live
  under old code. Rule 5 is what makes that survivable — follow it and the old
  code keeps working until you roll forward.

## Common commands

```bash
alembic upgrade head          # apply everything pending
alembic check                 # does the ORM still match this database?
alembic current               # what this database is on
alembic history --verbose     # the full chain
alembic downgrade -1          # step back one
alembic upgrade head --sql    # print SQL instead of running it (review / DBA handoff)
```

`-x url=...` overrides the target database for any of these.

## Configuration

`alembic.ini` deliberately leaves `sqlalchemy.url` unset. `env.py` reads it from
`remitx_api.config.Config.DATABASE_URL` — the same root `.env` the API and
worker use — so there is one source of truth and no second copy to drift.

Locally, the one-shot `migrate` service in
[../../docker-compose.dev.yml](../../docker-compose.dev.yml) runs
`alembic upgrade head` after Postgres is healthy; the `api` and `worker`
services wait for it to complete, so neither can boot on a stale schema.

In CI, the `migrate` job in
[../../.github/workflows/deploy.yml](../../.github/workflows/deploy.yml) runs
the same command against Neon using the per-environment
`MIGRATIONS_DATABASE_URL` secret, before `deploy-api` and `deploy-worker`, so a
failed migration blocks the rollout instead of leaving a running app on a schema
it does not match.
