#!/bin/sh
# Keep the node_modules volume in step with the host's manifests.
#
# docker-compose.dev.yml mounts a named volume over /app/node_modules, which
# shadows whatever `npm ci` installed into the image. Adding a dependency on
# the host therefore leaves the container with a stale tree that survives
# `up --build`, and Vite fails to resolve the new package. Reinstall whenever
# the manifests no longer match what the volume was built from.
set -e

STAMP=/app/node_modules/.manifest-hash

# package.json is hashed alongside the lockfile so a dependency edit that
# skipped `npm install` still triggers a run — npm ci then fails loudly about
# the out-of-sync lockfile instead of the container silently doing nothing.
current="$(cat /app/package.json /app/package-lock.json | md5sum | cut -d' ' -f1)"

if [ "$(cat "$STAMP" 2>/dev/null)" = "$current" ]; then
  echo "[entrypoint] node_modules up to date"
else
  echo "[entrypoint] manifests changed — running npm ci"
  npm ci
  echo "$current" >"$STAMP"
fi

exec "$@"
