# Relyo API

JSON REST API for the Relyo FX remittance platform. Built with Flask.

## Requirements

- Python 3.9+

## Setup

From the **repo root**:

```bash
cp .env.example .env
cd api
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Configuration

All environment variables live in the repo root `.env` (see `.env.example`). The API, frontend, and docker compose all read from that single file.

Docker injects the same variables into containers; SQLite defaults to `api/relyo.db` when `DATABASE_URL` is unset.

**Dev stack** (API + frontend + Postgres + Redis, foreground logs):

```bash
docker compose -f docker-compose.dev.yml up --build
```


| Variable           | Description                                | Default                                      |
| ------------------ | ------------------------------------------ | -------------------------------------------- |
| `PORT`             | HTTP port the dev server listens on        | `4200`                                       |
| `DEBUG`            | Enable Flask debug mode (`true` / `false`) | `false`                                      |
| `DATABASE_URL`     | SQLAlchemy database URI                    | `sqlite:///<api>/relyo.db`                   |
| `REDIS_URL`        | Redis connection URI for queues            | `redis://localhost:6379/0`                   |
| `POSTGRES_*`       | Postgres credentials (see root `.env`)     | `relyo` / `relyo` / `relyo`                  |


## Run

Development server:

```bash
python -m relyo_api
# or
relyo-api
```

The API listens on `http://0.0.0.0:<PORT>`.

Production-style entry point (e.g. with Gunicorn):

```bash
gunicorn wsgi:app
```



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
  wsgi.py
  relyo_api/
    app.py              # Application factory
    config.py           # Environment-based settings
    extensions.py       # Flask extensions (SQLAlchemy db)
    controllers/        # Request handling / business logic
    models/
      orm/              # SQLAlchemy ORM models (db.Model)
    repositories/       # Data access layer
    routes/             # HTTP blueprints (thin handlers)
      __init__.py       # Blueprint registration
      health.py
```

**Layering**

- `routes/` — HTTP concerns only; delegates to controllers
- `controllers/` — orchestrates use cases
- `repositories/` — SQLAlchemy data access via `Repository`
- `models/orm/` — SQLAlchemy entities (`db.Model`)
- `extensions.db` — shared SQLAlchemy instance

ORM models inherit from `db.Model` in `extensions.py`. In debug mode, tables are created automatically on startup.

Add new endpoints by creating a controller, optional repository, and a thin route blueprint registered in `routes/__init__.py`.