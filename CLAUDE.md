# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

RemitX is a prototype cross-border FX remittance platform (ZAR → RLUSD on the XRP Ledger **Testnet**) built for UCT ECO5040W. The full brief — user journey, fee model, limits, KYC, queue/worker requirements, deliverables — is in [docs/project-brief.md](docs/project-brief.md). Read it before designing any domain feature; requirements there are graded criteria, not suggestions.

Hard constraints from the brief:

- XRPL **Testnet only**. No mainnet accounts, no real funds, no production blockchain credentials.
- XRPL private keys stored in the DB must be encrypted, with the encryption key held outside that database. Keys must never be returned via the API, logged, or committed.
- Uploaded KYC documents live in object storage, never in Postgres. Uploads are POSTed to the API, which identifies the file by its leading bytes before writing it to the bucket; reads are signed URLs that expire in minutes, and every one is written to the audit log.
- RLUSD settlement must run asynchronously through a message queue with duplicate-message protection (no double-crediting).
- RLUSD transfer may not start until the simulated ZAR cash-in is confirmed.

Cloud deployment uses **Render** (API + worker web services, static frontend, Key Value), **Neon** (Postgres, and Object Storage for KYC documents), and **Clerk** (auth). See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) and [docs/superpowers/specs/2026-09-12-render-migration-design.md](docs/superpowers/specs/2026-09-12-render-migration-design.md).

**Cloud environments:** `main` branch → QA stack; `stable` → Production. Async settlement is **Celery + Redis** — local Docker worker; cloud worker is a free Render web service woken via `WORKER_WAKE_URL`.

## Layout

Monorepo with two apps sharing one env file:

- [api/](api/) — FastAPI JSON REST API (`remitx_api` package)
- [frontend/](frontend/) — React Router v7 (SPA) + Tailwind v4 + shadcn/ui
- [infra/](infra/) — Terraform (Render). Azure destroy roots: [infra/legacy-azure/](infra/legacy-azure/)
- [api/alembic/](api/alembic/) — database migrations (naming standard in its README)
- [frontend/openapi.json](frontend/openapi.json) — the API contract, exported from FastAPI; the frontend client is generated from it
- [scripts/hooks/](scripts/hooks/) — pre-commit hook implementations
- [tools/seeder/](tools/seeder/) — local-only QA test-data seeder (NiceGUI). Never deployed; drives the backend's own controllers, services and worker tasks. See its [README](tools/seeder/README.md) and [ADR 0001](docs/adr/0001-qa-seeder-drives-the-service-layer.md)
- [tools/loadtest/](tools/loadtest/) — Locust load test on a throwaway Docker stack, seeded by the seeder; never calls Clerk, the rate API or the XRPL. Profiles can sweep API/worker compute after one seed; each run emits a commit-able `report.canvas.tsx`. See its [README](tools/loadtest/README.md)
- [Makefile](Makefile) — shortcuts for the commands below; `make` lists them
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — Render + Neon + Clerk setup
- [.github/workflows/](.github/workflows/) — CI and Render deploy on `main` / `stable`

## Environment configuration

**A single root `.env` is the only source of config** for the API, the frontend, and both compose files. [api/remitx_api/config.py](api/remitx_api/config.py) walks up from the package to load the *repo-root* `.env` explicitly — there is no `api/.env`. Copy `.env.minimal.example` to `.env` on first setup (only what local dev needs; everything else has a default). Adding a new setting means updating `.env.example` too, and `.env.minimal.example` as well if local dev can't run without it.

`.env` is gitignored and a pre-commit hook hard-blocks committing any file named `.env` or `.env.*` (templates named `*.example` excepted).

Two exceptions to the single `.env`: the seeder's QA target reads `tools/seeder/.env.qa` (gitignored), so QA credentials never sit in the file the API uses locally; and the load test's throwaway stack (and the seeder's `loadtest` target) reads the committed `tools/loadtest/loadtest.env`, which holds nothing secret, so a run can never pick up real keys.

## Commands

`make` lists shortcuts for most of the commands below.

### Docker (full stack: API + frontend + Postgres + Redis + MinIO)

```bash
docker compose -f docker-compose.dev.yml up --build   # foreground logs
docker compose -f docker-compose.dev.yml down
```

`docker-compose.yml` (no `-f`) is API + frontend only, no infrastructure.

### API

```bash
cd api && source .venv/bin/activate
pip install -e '.[dev]'

python -m remitx_api                 # dev server on 0.0.0.0:$PORT (4200)
uvicorn asgi:app --host 0.0.0.0 --port 4200   # production-style entry point

pytest                              # all tests
pytest tests/test_health.py::test_health_returns_ok   # single test
TEST_DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@localhost:PORT/postgres pytest -m postgres
                                    # Postgres lane (row locks etc.): makes and drops its own migrated DB; skipped when unset
ruff check --fix . && ruff format . # lint + format (config in pyproject.toml)

alembic upgrade head                # apply migrations
alembic check                       # ORM vs schema drift check
alembic revision --autogenerate -m "..."   # new migration (review before committing)
```

Migrations are applied automatically by the one-shot `migrate` service in
`docker-compose.dev.yml`; the api and worker wait for it. See
[api/alembic/README.md](api/alembic/README.md).

### Frontend

```bash
cd frontend
npm ci
npm run dev          # vite dev server on 5173
npm run lint         # typecheck + prettier --check
npm run generate:api # Hey API client from openapi.json (dev/build/typecheck run it)
npm run typecheck    # generate:api && react-router typegen && tsc
npm test             # vitest: unit tests for app/lib (*.test.ts)
npm run format       # prettier --write
npx shadcn@latest add <component>
```

### Seeder (local only)

```bash
cd tools/seeder && source .venv/bin/activate
pip install -e ../../api -e '.[dev]'
python -m remitx_seeder              # UI on http://127.0.0.1:8090
pytest                              # needs SEEDER_TEST_DATABASE_URL (a Postgres it can create DBs on)
```

A backend change that breaks the seeder fails its CI job: update the story in `tools/seeder/remitx_seeder/stories/`. Writes that bypass product flows go only in `direct.py`.

### Load test (Docker only)

```bash
make loadtest        # build, seed once, run Locust (optional compute sweep), delete stack
make loadtest-down   # delete the stack after an interrupted or KEEP_STACK=1 run
make loadtest-canvas RESULTS=tools/loadtest/results/<ts>  # rebuild summary + canvas
```

Each run writes `tools/loadtest/results/<timestamp>/` with commit-able
`profile.json`, `summary.json`, and `report.canvas.tsx` (brief performance
metrics). Locust CSVs/HTML stay gitignored under `compute/<name>/`. Edit
`tools/loadtest/profiles/*.json` for population, Locust user steps, burn
timings, CPU/memory, and optional `compute` sweep (`LOADTEST_PROFILE`, default
`default`; use `compute-sweep` for API 0.1 then 1.0 CPU). Locust tokens use
`CLERK_JWT_KEY`; the worker's XRPL burn is simulated with a delay calibrated by
`tools/loadtest/qa_xrpl_timings.sql`.

### Git hooks

```bash
./scripts/setup-hooks.sh                  # installs pre-commit + prints prereqs
python3 -m pre_commit run --all-files
```

Pre-commit regenerates `frontend/openapi.json` when `api/remitx_api/` changes, and runs gitleaks (config: [.gitleaks.toml](.gitleaks.toml), with custom XRPL-seed and DB-URL rules), the `.env` block, ruff fix+format on staged Python, `pytest`, and prettier + `npm run typecheck` on the frontend. Hooks re-`git add` files they auto-fix.

## API architecture

Application-factory FastAPI app ([api/remitx_api/app.py](api/remitx_api/app.py)) with a strict four-layer split:

```
routes/       HTTP only — APIRouter handlers, no logic
controllers/  use-case orchestration
repositories/ SQLAlchemy data access via the generic Repository
models/orm/   SQLAlchemy ORM entities (Base)
extensions.py shared `db` session + DeclarativeBase
```

Adding an endpoint means: ORM model → repository (if needed) → controller → thin route in `routes/`, registered in [api/remitx_api/routes/\_\_init\_\_.py](api/remitx_api/routes/__init__.py) via `register_routers` → `python scripts/export_openapi.py` to update the spec the frontend client is generated from.

**The OpenAPI spec is the frontend contract** ([api/remitx_api/openapi.py](api/remitx_api/openapi.py)). Every route needs a `summary=` (plus a docstring for anything non-obvious) and `responses=error_responses(...)` for the refusals it can answer; its router carries one `Tag`. Tags are dotted (`admin.users`) and become the client namespace (`api.admin.users`). The operation id is the handler's function name, so name handlers as the client function should read (`list_roles` → `listRoles`) and keep them unique. Request/response models inherit `Schema`, and timestamps use `UtcDateTime`. [api/tests/test_openapi.py](api/tests/test_openapi.py) enforces all of this and fails on a stale `frontend/openapi.json`.

Things that bite:

- **Every ORM model must inherit from `Base` in [api/remitx_api/extensions.py](api/remitx_api/extensions.py) and be imported in [api/remitx_api/models/orm/\_\_init\_\_.py](api/remitx_api/models/orm/__init__.py)** or its table is invisible to SQLAlchemy metadata and never created.
- **Alembic owns the Postgres schema in every environment** ([api/alembic/](api/alembic/), see [api/alembic/README.md](api/alembic/README.md)). `db.create_all()` runs only when `CREATE_ALL` is true, which is `TestConfig` only — tests build a throwaway SQLite schema. Adding a table means an ORM model *and* a migration; `alembic check` must report no drift.
- **`remitx_api/__init__.py` eagerly imports `create_app`**, so importing any `remitx_api` submodule drags in the whole route tree. `remitx_worker` may import `remitx_api`; the reverse creates a circular import at worker boot. The API talks to the worker by task name over the broker, never by importing it.
- `Repository[T, ID]` ([api/remitx_api/repositories/repository.py](api/remitx_api/repositories/repository.py)) commits inside `save`/`delete`. Multi-entity use cases that need one transaction should not chain repository calls — use `db.session` directly in the controller.
- Config classes are the switch for environments: `Config` reads env vars; `TestConfig` forces in-memory SQLite. Tests get a client via the `client` fixture in [api/tests/conftest.py](api/tests/conftest.py), which builds a fresh app per test.
- `DATABASE_URL` unset falls back to SQLite at `api/remitx.db`; compose overrides it to Postgres.

**Python version:** `requires-python >= 3.11`, ruff targets `py311`, and the
Docker image is `python:3.11` — local venvs, CI, and production all run the
same minor. The floor is 3.11 because `clerk-backend-api` requires >= 3.10;
match the Docker image rather than the SDK minimum so no version gap can open
between local and production.

## Frontend architecture

React Router v7 in **SPA mode** ([frontend/react-router.config.ts](frontend/react-router.config.ts)) — static client build deployed to a Render static site.

- Routes are declared explicitly in [frontend/app/routes.ts](frontend/app/routes.ts), not by file-system convention. New pages must be added there.
- Route types come from `react-router typegen` into `.react-router/types` and are imported as `./+types/<route>`. Run `npm run typecheck` (which regenerates them) after adding a route, or types will be stale/missing.
- Path alias `~/*` → `app/*`.
- Tailwind v4 configured entirely in CSS ([frontend/app/app.css](frontend/app/app.css)) — no `tailwind.config`. shadcn uses the `base-lyra` style over `@base-ui/react`, Phosphor icons, and CSS variables.
- Prettier enforces **no semicolons**, double quotes, 2-space indent, 80 cols, with Tailwind class sorting (`cn`, `cva` aware). Match it; the hook rewrites files otherwise.
- API calls go through the Hey API client generated into `app/client/` (gitignored), namespaced by OpenAPI tag: `useQuery(api.admin.roles.listRoles())`, `useMutation(api.admin.users.grantUserRole())`, raw requests via `sdk.*`, types from `~/client`. Don't import the flat `sdk.gen` / `react-query.gen` modules. Never hand-write request functions or response types. See [frontend/README.md](frontend/README.md#calling-the-api).
- API base URL reaches the client via `VITE_API_URL`.
- Theme: `next-themes` in [frontend/app/components/theme-provider.tsx](frontend/app/components/theme-provider.tsx); light / dark / auto toggle in [frontend/app/components/theme-toggle.tsx](frontend/app/components/theme-toggle.tsx). Palette tokens live in `app.css` (`:root` and `.dark`).

### UI component standard

**Default approach for all frontend UI work:** compose pages from **shadcn/ui** and **Aceternity UI** components. Use **Tailwind and CSS for layout only** — not for ad-hoc component styling.

| Layer | Use for | Install / location |
|-------|---------|-------------------|
| **shadcn/ui** | Buttons, cards, badges, forms, dialogs, and other interactive UI; component look-and-feel via variants and theme tokens | `npx shadcn@latest add <component>` → [frontend/app/components/ui/](frontend/app/components/ui/) |
| **Aceternity UI** | Motion, backgrounds, spotlight, 3D tilt, and other stylized effects | `npx shadcn@latest add @aceternity/<name>` → [frontend/app/components/aceternity/](frontend/app/components/aceternity/) (move from `frontend/components/` if the CLI writes there) |
| **Tailwind / CSS** | Page and section layout: `flex`, `grid`, `gap`, `max-w-*`, `px-*`, `w-full`, positioning, responsive breakpoints | Route files and thin layout wrappers only |
| **Theme tokens** | Colors, radius, typography | [frontend/app/app.css](frontend/app/app.css) CSS variables; consume via shadcn classes (`bg-background`, `text-muted-foreground`, etc.) |

Rules:

- Prefer an existing shadcn or Aceternity component over a custom styled element.
- Do **not** use Tailwind color, border, shadow, or typography utilities to reinvent what a shadcn variant or Aceternity component already provides.
- Icons: `@phosphor-icons/react` (project default in [frontend/components.json](frontend/components.json)).
- More detail: [frontend/README.md](frontend/README.md) and [.cursor/rules/frontend-ui.mdc](.cursor/rules/frontend-ui.mdc).

## Agent skills

### Issue tracker

Issues live in GitHub Issues for SianC7/RemitX_Stokvel (via the `gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-label vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
