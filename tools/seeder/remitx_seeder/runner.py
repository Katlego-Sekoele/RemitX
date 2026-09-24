"""Every database operation runs here, in its own process.

The UI starts `python -m remitx_seeder <command> --target <name> ...` and reads
its stdout: one JSON object per line, `{"type": "log" | "progress" | "result" |
"error", ...}`. A process per operation because:

- the target's environment has to be loaded before `remitx_api` is imported
  (settings.py explains why), and a process can only import it once;
- a seed run moves the process's clock (clock.py), which must never touch the
  UI's own timers and websockets;
- a crash mid-run cannot take the UI down with it.

It also works from a terminal, which is handy for debugging, but it is the
UI's protocol rather than a supported CLI.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import traceback
from datetime import UTC, datetime

from remitx_seeder.guards import clerk_mode, evaluate, require_safe_target
from remitx_seeder.settings import (
    REPO_ROOT,
    RUNS_DIR,
    load_target_env,
    load_targets,
    read_target_env,
)

COMMANDS = ("status", "verify", "schema", "people", "seed", "reset")


def emit(event: dict) -> None:
    sys.stdout.write(json.dumps(event, default=str) + "\n")
    sys.stdout.flush()


class _EmitHandler(logging.Handler):
    """Backend and worker log lines, as protocol events, without tracebacks
    (a simulated failed burn logs one on purpose)."""

    def emit(self, record: logging.LogRecord) -> None:
        level = record.levelname.lower()
        emit(
            {
                "type": "log",
                "level": level,
                "message": f"{record.name}: {record.getMessage()}",
            }
        )


def _quiet_logging() -> None:
    root = logging.getLogger()
    root.handlers[:] = [_EmitHandler()]
    root.setLevel(logging.WARNING)


def git_sha() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _init_db():
    from remitx_api.config import Config
    from remitx_api.extensions import db

    db.init(Config.DATABASE_URL)
    return db


def _clerk(env: dict[str, str]):
    from remitx_seeder.clerk import FakeClerkGateway, SdkClerkGateway

    key = env.get("CLERK_SECRET_KEY", "").strip()
    return SdkClerkGateway(key) if key else FakeClerkGateway()


def cmd_status(target: str, env: dict[str, str], args) -> dict:
    from sqlalchemy import text

    status: dict = {"clerk_mode": clerk_mode(env)}
    db = _init_db()
    token = db.open_session()
    try:
        status["alembic_revision"] = db.session.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()
        status["users"] = db.session.execute(
            text("SELECT count(*) FROM users")
        ).scalar()
        status["seeded_users"] = db.session.execute(
            text(
                "SELECT count(*) FROM users WHERE email LIKE '%+clerk_test@%' "
                "OR clerk_user_id LIKE 'seed\\_%'"
            )
        ).scalar()
        try:
            from remitx_seeder.engine import preflight

            preflight()
            status["ready"] = True
            status["ready_detail"] = "The platform accounts are in place."
        except Exception as exc:  # noqa: BLE001
            status["ready"] = False
            status["ready_detail"] = str(exc)
    finally:
        db.close_session(token)
    if status["clerk_mode"] == "clerk":
        try:
            status["clerk_users"] = _clerk(env).user_count()
        except Exception as exc:  # noqa: BLE001
            status["clerk_users"] = f"unavailable ({type(exc).__name__})"
    return status


def cmd_verify(target: str, env: dict[str, str], args) -> dict:
    from remitx_seeder.verify import run_verify

    db = _init_db()
    token = db.open_session()
    try:
        return run_verify(db.session, check_chain=args.chain).as_dict()
    finally:
        db.close_session(token)


def cmd_schema(target: str, env: dict[str, str], args) -> dict:
    from remitx_seeder import schema

    db = _init_db()
    token = db.open_session()
    try:
        return {"tables": schema.as_dicts(schema.describe(db.session))}
    finally:
        db.close_session(token)


def cmd_people(target: str, env: dict[str, str], args) -> dict:
    from sqlalchemy import text

    db = _init_db()
    token = db.open_session()
    try:
        rows = (
            db.session.execute(
                text(
                    """
                SELECT u.first_name, u.full_name, u.email, u.clerk_user_id,
                       u.base_reference, u.country, u.created_at,
                       (SELECT string_agg(r.name, ', ' ORDER BY r.name)
                          FROM user_roles ur JOIN roles r ON r.role_id = ur.role_id
                         WHERE ur.user_id = u.id AND ur.revoked_at IS NULL) AS roles,
                       (SELECT a.status FROM kyc_applications a
                         WHERE a.user_id = u.id ORDER BY a.created_at DESC LIMIT 1)
                         AS kyc_status,
                       (SELECT a.account_balance FROM accounts a
                         WHERE a.user_id = u.id AND a.type = 'USER'
                           AND a.account_currency = 'ZAR') AS zar_balance
                  FROM users u
                 WHERE u.email LIKE '%+clerk_test@%' OR u.clerk_user_id LIKE 'seed\\_%'
                 ORDER BY u.created_at
                 LIMIT 1000
                """
                )
            )
            .mappings()
            .all()
        )
    finally:
        db.close_session(token)
    return {
        "people": [
            {
                **dict(row),
                "can_sign_in": row["clerk_user_id"].startswith("user_"),
            }
            for row in rows
        ]
    }


def cmd_seed(target: str, env: dict[str, str], args) -> dict:
    from remitx_api.config import Config
    from remitx_api.services.object_storage import S3ObjectStorage

    from remitx_seeder.engine import run_seed
    from remitx_seeder.live_tail import make_live_tail
    from remitx_seeder.scenario import load_scenario

    scenario = load_scenario(args.scenario)
    if args.seed is not None:
        scenario.seed = args.seed
    if args.live_settlements is not None:
        scenario.live_settlements = args.live_settlements
    spec = load_targets()[target]
    _init_db()
    live_tail = None
    if scenario.live_settlements > 0:
        live_tail = make_live_tail(
            env.get("SEEDER_API_URL") or spec.api_url,
            env.get("SEEDER_API_ORIGIN") or spec.api_origin,
        )
    started_at = datetime.now(UTC)
    summary = run_seed(
        scenario,
        clerk=_clerk(env),
        clerk_enabled=clerk_mode(env) == "clerk",
        storage=S3ObjectStorage.from_config(Config()),
        emit=emit,
        live_tail=live_tail,
        check_chain=args.chain,
    )
    manifest = {
        "target": target,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "git_sha": git_sha(),
        **summary,
    }
    RUNS_DIR.mkdir(exist_ok=True)
    path = RUNS_DIR / f"{summary['run_id']}-{target}-{scenario.name}.json"
    path.write_text(json.dumps(manifest, indent=2, default=str))
    manifest["manifest_path"] = str(path)
    return manifest


def cmd_reset(target: str, env: dict[str, str], args) -> dict:
    from remitx_seeder.reset import reset

    clerk = _clerk(env) if clerk_mode(env) == "clerk" else None
    return reset(target, args.confirm or "", clerk, emit)


HANDLERS = {
    "status": cmd_status,
    "verify": cmd_verify,
    "schema": cmd_schema,
    "people": cmd_people,
    "seed": cmd_seed,
    "reset": cmd_reset,
}


def parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="remitx_seeder")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--target", required=True, choices=sorted(load_targets()))
    parser.add_argument("--scenario", default="default")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--live-settlements", type=int, dest="live_settlements")
    parser.add_argument(
        "--chain", action="store_true", help="also check the treasury on chain"
    )
    parser.add_argument("--confirm", help='reset only: the phrase "reset <target>"')
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse(argv)
    target = args.target
    spec = load_targets().get(target)
    env = read_target_env(target)
    report = evaluate(target, env, spec)
    emit({"type": "guards", **report.as_dict()})
    try:
        require_safe_target(target, env, spec)
        # Only now, with the guards passed, does the target's configuration
        # reach os.environ, and with it remitx_api.
        load_target_env(target)
        _quiet_logging()
        result = HANDLERS[args.command](target, env, args)
        emit({"type": "result", "command": args.command, "result": result})
        return 0
    except Exception as exc:  # noqa: BLE001 — reported to the UI
        emit(
            {
                "type": "error",
                "command": args.command,
                "message": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(limit=8),
            }
        )
        return 1
