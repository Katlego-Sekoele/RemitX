"""The checks every run passes before it touches anything.

Pure functions of the target's environment and `targets.json`, so they can be
evaluated (and shown in the UI) without connecting to anything. Every command
that writes calls `require_safe_target`; a failed check is a refusal, never a
warning.

What they defend against, in order:

1. **Production Clerk.** A `sk_live_` key belongs to a production Clerk
   instance. Production is never a development instance and QA always is, so
   this check alone keeps a run away from prod whatever else is misconfigured.
2. **An unexpected database.** The database host must be on the target's
   allowlist in `targets.json`. An empty allowlist refuses everything.
3. **A mislabelled env file.** The QA env file must say `SEEDER_TARGET=qa`, so
   a copy of it used under another target is refused.
4. **An unexpected bucket.** KYC documents may only go to the target's bucket.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit

from remitx_seeder.settings import TargetSpec

CLERK_LIVE_PREFIX = "sk_live_"
CLERK_TEST_PREFIX = "sk_test_"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class GuardReport:
    target: str
    checks: tuple[Check, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    @property
    def failures(self) -> tuple[Check, ...]:
        return tuple(check for check in self.checks if not check.ok)

    def as_dict(self) -> dict:
        return {
            "target": self.target,
            "ok": self.ok,
            "checks": [
                {"name": check.name, "ok": check.ok, "detail": check.detail}
                for check in self.checks
            ],
        }


class UnsafeTargetError(RuntimeError):
    """A guard failed. The message lists every failed check."""


def database_host(database_url: str) -> str | None:
    """The host a SQLAlchemy URL connects to, without its credentials."""
    if not database_url:
        return None
    # `postgresql+psycopg2://user:pass@host:5432/db` parses as a URL once the
    # driver suffix is irrelevant; urlsplit keeps the password out of anything
    # we return.
    return urlsplit(database_url).hostname


def clerk_mode(env: dict[str, str]) -> str:
    """`clerk` when synthetic people become real Clerk users, else
    `database-only` (no key configured: every person gets a `seed_…` id)."""
    return "clerk" if env.get("CLERK_SECRET_KEY", "").strip() else "database-only"


def evaluate(target: str, env: dict[str, str], spec: TargetSpec | None) -> GuardReport:
    checks: list[Check] = []

    if spec is None:
        checks.append(Check("target", False, f"{target!r} is not in targets.json"))
        return GuardReport(target, tuple(checks))
    checks.append(Check("target", True, spec.description or target))

    declared = env.get("SEEDER_TARGET", "").strip()
    if target == "local" and not declared:
        checks.append(
            Check("env file", True, "repo-root .env (no SEEDER_TARGET needed)")
        )
    elif declared == target:
        checks.append(Check("env file", True, f"SEEDER_TARGET={declared}"))
    else:
        checks.append(
            Check(
                "env file",
                False,
                f"the env file says SEEDER_TARGET={declared or '(unset)'}, "
                f"but this run's target is {target}",
            )
        )

    clerk_key = env.get("CLERK_SECRET_KEY", "").strip()
    if clerk_key.startswith(CLERK_LIVE_PREFIX):
        checks.append(
            Check(
                "clerk",
                False,
                "CLERK_SECRET_KEY is a production key (sk_live_). The seeder only "
                "runs against Clerk development instances.",
            )
        )
    elif clerk_key and not clerk_key.startswith(CLERK_TEST_PREFIX):
        checks.append(
            Check("clerk", False, "CLERK_SECRET_KEY is not a Clerk secret key")
        )
    elif clerk_key:
        checks.append(Check("clerk", True, "development instance (sk_test_)"))
    else:
        checks.append(
            Check("clerk", True, "no key: people are database-only (seed_… ids)")
        )

    host = database_host(env.get("DATABASE_URL", ""))
    if host is None:
        checks.append(Check("database", False, "DATABASE_URL is not set"))
    elif host in spec.database_hosts:
        checks.append(Check("database", True, f"{host} is allowlisted for {target}"))
    else:
        allowed = ", ".join(spec.database_hosts) or "nothing yet"
        checks.append(
            Check(
                "database",
                False,
                f"{host} is not allowlisted for {target} (targets.json allows: "
                f"{allowed})",
            )
        )

    bucket = env.get("OBJECT_STORAGE_BUCKET", "kyc-documents").strip()
    if bucket in spec.buckets:
        checks.append(Check("bucket", True, f"{bucket} is allowlisted for {target}"))
    else:
        checks.append(
            Check(
                "bucket",
                False,
                f"{bucket} is not allowlisted for {target} (targets.json allows: "
                f"{', '.join(spec.buckets) or 'nothing'})",
            )
        )

    return GuardReport(target, tuple(checks))


def require_safe_target(
    target: str, env: dict[str, str], spec: TargetSpec | None
) -> GuardReport:
    report = evaluate(target, env, spec)
    if not report.ok:
        reasons = "; ".join(f"{c.name}: {c.detail}" for c in report.failures)
        raise UnsafeTargetError(f"Refusing to run against {target}: {reasons}")
    return report
