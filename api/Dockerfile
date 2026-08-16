FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml .
COPY relyo_api/ relyo_api/

RUN pip install --upgrade pip && pip install -e .

EXPOSE 4200

CMD ["python", "-m", "relyo_api"]
