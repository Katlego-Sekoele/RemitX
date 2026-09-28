# RemitX API

JSON REST API for the RemitX FX remittance platform. Built with FastAPI.

## Requirements

- Python 3.9+

## Setup

From the **repo root**:

```bash
cp .env.minimal.example .env   # then fill in the blanks
cd api
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## Configuration

All environment variables live in the repo root `.env`. `.env.minimal.example` lists what local development needs; `.env.example` documents every setting. The API, frontend, and docker compose all read from that single file.

Docker injects the same variables into containers; SQLite defaults to `api/remitx.db` when `DATABASE_URL` is unset.

**Dev stack** (API + frontend + Postgres + Redis, foreground logs):

```bash
docker compose -f docker-compose.dev.yml up --build
```


| Variable           | Description                                | Default                                      |
| ------------------ | ------------------------------------------ | -------------------------------------------- |
| `PORT`             | HTTP port the dev server listens on        | `4200`                                       |
| `DEBUG`            | Enable auto-reload and `create_all()`      | `false`                                      |
| `DATABASE_URL`     | SQLAlchemy database URI                    | `sqlite:///<api>/remitx.db`                   |
| `REDIS_URL`        | Redis URI for Celery broker/backend       | `redis://localhost:6379/0`                   |
| `POSTGRES_*`       | Postgres credentials (see root `.env`)     | `remitx` / `remitx` / `remitx`                  |


## Run

Development server:

```bash
python -m remitx_api
# or
remitx-api
```

The API listens on `http://0.0.0.0:<PORT>`. OpenAPI docs at `/docs`.

Production-style entry point (e.g. with Uvicorn locally):

```bash
uvicorn asgi:app --host 0.0.0.0 --port 4200
```

## Cloud (Azure Container Apps)

Deploy as a container image to GHCR; Uvicorn entry point via `Dockerfile`. See [docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md).

- Async settlement: Celery producer in API; Redis + worker on Container Apps


## Endpoints


| Method | Path      | Response           |
| ------ | --------- | ------------------ |
| `GET`  | `/health` | `{"status": "ok"}` |


Example:

```bash
curl http://localhost:4200/health
```



## Project structure

```
api/
  pyproject.toml
  asgi.py
  remitx_api/
    app.py              # Application factory
    config.py           # Environment-based settings
    extensions.py       # SQLAlchemy Base + session
    controllers/        # Request handling / business logic
    models/
      orm/              # SQLAlchemy ORM models (Base)
    repositories/       # Data access layer
    routes/             # HTTP routers (thin handlers)
      __init__.py       # Router registration
      health.py
```

**Layering**

- `routes/` — HTTP concerns only; delegates to controllers
- `controllers/` — orchestrates use cases
- `repositories/` — SQLAlchemy data access via `Repository`
- `models/orm/` — SQLAlchemy entities (`Base`)
- `extensions.db` — shared database session

ORM models inherit from `Base` in `extensions.py`. In debug mode, tables are created automatically on startup.

Add new endpoints by creating a controller, optional repository, and a thin route registered in `routes/__init__.py`.
