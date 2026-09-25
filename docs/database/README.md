# Database schema

`schema.dbml` is the Postgres schema the Alembic migrations build, in
[DBML](https://dbml.dbdiagram.io). It is **generated: never edit it by hand**.
The living docs (Storybook's **Database** section) read it, and so can
[dbdiagram.io](https://dbdiagram.io) if you want a diagram.

After adding a migration, regenerate it and commit it with the migration:

```bash
scripts/generate-dbml.sh            # rewrite docs/database/schema.dbml
scripts/generate-dbml.sh --check    # what CI runs: exit 1 if it is stale
```

The script migrates a throwaway database to head, reads it with the
dbdiagram CLI (`db2dbml`), then sorts the parts the CLI emits in no stable
order, so the file only changes when the schema does. It needs a Postgres
server it may create a database on: `DBML_DATABASE_URL`, or else
`DATABASE_URL` from the root `.env`. The compose Postgres
(`docker compose -f docker-compose.dev.yml up -d postgres`) works. It also
needs the API environment (`cd api && pip install -e '.[dev]'`), the
frontend's (`cd frontend && npm ci`) and Node >= 22.18.

A change here shows up as a readable diff in review, and on a pull request
CI lists the journeys, operations and screens it touches.
