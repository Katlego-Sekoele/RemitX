# The seeder plus the load test's prepare step. Both drive the backend's own
# code, so the API package is installed next to them. Built from the repo root
# (see seeder.Dockerfile.dockerignore for what the build can see).
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY api/ api/
COPY tools/seeder/ tools/seeder/
COPY tools/loadtest/ tools/loadtest/

RUN pip install --upgrade pip && pip install -e api -e tools/seeder

# run.sh overrides the command to pass the profile's extracted seed scenario.
CMD ["python", "tools/loadtest/prepare.py"]
