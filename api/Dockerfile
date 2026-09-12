FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml .
COPY remitx_api/ remitx_api/
COPY remitx_worker/ remitx_worker/
COPY alembic.ini .
COPY alembic/ alembic/
COPY asgi.py .

RUN pip install --upgrade pip && pip install -e .

EXPOSE 4200

CMD ["python", "-m", "remitx_api"]
