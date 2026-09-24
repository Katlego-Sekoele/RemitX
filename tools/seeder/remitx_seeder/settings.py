"""Where a target's configuration comes from, and loading it.

A *target* is the environment a run writes to: `local` (your Docker Compose
stack, configured by the repo-root `.env`) or `qa` (the QA stack, configured by
`tools/seeder/.env.qa`). The allowlists every target must satisfy live in
`tools/seeder/targets.json`, which is committed: widening what the seeder may
touch is a reviewed change, never an env var.

`remitx_api.config.Config` reads most settings when the module is imported, so
a target's environment has to be in `os.environ` *before* anything imports
`remitx_api`. That is why every command that touches a database runs in its own
process (see `runner.py`) and calls `load_target_env` first.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

SEEDER_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SEEDER_ROOT.parent.parent
TARGETS_FILE = SEEDER_ROOT / "targets.json"
RUNS_DIR = SEEDER_ROOT / "runs"
SCENARIOS_DIR = SEEDER_ROOT / "scenarios"

TARGET_ENV_FILES = {
    "local": REPO_ROOT / ".env",
    "qa": SEEDER_ROOT / ".env.qa",
}


@dataclass(frozen=True)
class TargetSpec:
    name: str
    description: str
    database_hosts: tuple[str, ...]
    buckets: tuple[str, ...]
    api_url: str
    api_origin: str


def load_targets(path: Path = TARGETS_FILE) -> dict[str, TargetSpec]:
    raw = json.loads(path.read_text())
    return {
        name: TargetSpec(
            name=name,
            description=spec.get("description", ""),
            database_hosts=tuple(spec.get("database_hosts", [])),
            buckets=tuple(spec.get("buckets", [])),
            api_url=spec.get("api_url", ""),
            api_origin=spec.get("api_origin", ""),
        )
        for name, spec in raw.items()
    }


def env_file_for(target: str) -> Path:
    try:
        return TARGET_ENV_FILES[target]
    except KeyError:
        raise ValueError(f"Unknown target {target!r}") from None


def read_target_env(target: str) -> dict[str, str]:
    """The target's env file as a dict, without touching `os.environ`."""
    path = env_file_for(target)
    if not path.exists():
        return {}
    return {key: value or "" for key, value in dotenv_values(path).items()}


# Connection and credential settings a non-local target must never borrow.
# `remitx_api.config` also loads the repo-root `.env` (without overriding), so
# a key the target's file leaves out would otherwise be filled with your local
# one. These are blanked instead: missing means missing.
ISOLATED_KEYS = (
    "DATABASE_URL",
    "CLERK_SECRET_KEY",
    "CLERK_JWKS_URL",
    "OBJECT_STORAGE_ENDPOINT_URL",
    "OBJECT_STORAGE_PUBLIC_ENDPOINT_URL",
    "OBJECT_STORAGE_BUCKET",
    "OBJECT_STORAGE_ACCESS_KEY_ID",
    "OBJECT_STORAGE_SECRET_ACCESS_KEY",
    "PLATFORM_WALLET_ADDRESS",
    "PLATFORM_WALLET_SEED_ENCRYPTED",
    "XRPL_ENCRYPTION_KEY",
    "WORKER_WAKE_URL",
    "SEEDER_API_URL",
    "SEEDER_API_ORIGIN",
)


def load_target_env(target: str) -> dict[str, str]:
    """Put the target's env file into `os.environ`, overriding what is there.

    Overriding matters: a developer's shell may already export a
    `DATABASE_URL` for something else, and the file the target names is the
    only configuration a run may use.
    """
    values = read_target_env(target)
    if target != "local":
        for key in ISOLATED_KEYS:
            os.environ[key] = ""
    os.environ.update(values)
    return values
