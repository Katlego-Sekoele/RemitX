"""Load-test profiles: population + Locust shape + stack limits in one JSON.

Profiles live in `tools/loadtest/profiles/`. `run.sh` loads one, writes the
`seed` block for the seeder, and exports the rest as compose/Locust/worker
env vars. Edit a profile (or add another) instead of passing LOADTEST_* knobs.

  python loadtest_profile.py apply default --write-seed /tmp/seed.json --exports
  python loadtest_profile.py compute-steps compute-sweep
  LOADTEST_PROFILE=default make loadtest
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROFILES_DIR = HERE / "profiles"
SEEDER_ROOT = HERE.parent / "seeder"

_MEMORY = re.compile(r"^\d+(\.\d+)?[kKmMgGtT]?$")
_COMPUTE_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class LocustShape:
    steps: list[int]
    step_seconds: int
    spawn_rate: float


@dataclass(frozen=True)
class Burn:
    p50_s: float
    p95_s: float
    failure_rate: float


@dataclass(frozen=True)
class ServiceLimits:
    cpus: float
    memory: str


@dataclass(frozen=True)
class WorkerLimits(ServiceLimits):
    celery_concurrency: int


@dataclass(frozen=True)
class PostgresLimits(ServiceLimits):
    # Neon Free at 2 CU; see https://neon.com/docs/manage/computes
    max_connections: int


@dataclass(frozen=True)
class DatabasePool:
    """SQLAlchemy QueuePool per process (API / each Celery child)."""

    pool_size: int
    max_overflow: int


@dataclass(frozen=True)
class ComputeStep:
    """One API / worker / Postgres size to run Locust against after a shared seed."""

    name: str
    api: ServiceLimits
    worker: WorkerLimits
    postgres: ServiceLimits

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "api": {"cpus": self.api.cpus, "memory": self.api.memory},
            "worker": {
                "cpus": self.worker.cpus,
                "memory": self.worker.memory,
                "celery_concurrency": self.worker.celery_concurrency,
            },
            "postgres": {
                "cpus": self.postgres.cpus,
                "memory": self.postgres.memory,
            },
        }


@dataclass(frozen=True)
class Profile:
    name: str
    description: str
    seed: dict
    locust: LocustShape
    burn: Burn
    api: ServiceLimits
    worker: WorkerLimits
    postgres: PostgresLimits
    database_pool: DatabasePool
    compute: tuple[ComputeStep, ...]

    def compute_steps(self) -> tuple[ComputeStep, ...]:
        """Effective sweep: explicit `compute` or one step from top-level limits."""
        if self.compute:
            return self.compute
        return (
            ComputeStep(
                name="default",
                api=self.api,
                worker=self.worker,
                postgres=ServiceLimits(
                    cpus=self.postgres.cpus, memory=self.postgres.memory
                ),
            ),
        )

    def exports(self, *, compute: ComputeStep | None = None) -> dict[str, str]:
        """Env vars compose, Locust and the fake worker already understand.

        When ``compute`` is set, API/worker/postgres CPU+memory come from that
        step; Locust shape, burn, max_connections and pool stay profile-level.
        """
        step = compute or self.compute_steps()[0]
        return {
            "LOADTEST_STEPS": ",".join(str(n) for n in self.locust.steps),
            "LOADTEST_STEP_SECONDS": str(self.locust.step_seconds),
            "LOADTEST_SPAWN_RATE": str(self.locust.spawn_rate),
            "LOADTEST_BURN_P50_S": str(self.burn.p50_s),
            "LOADTEST_BURN_P95_S": str(self.burn.p95_s),
            "LOADTEST_BURN_FAILURE_RATE": str(self.burn.failure_rate),
            "LOADTEST_CELERY_CONCURRENCY": str(step.worker.celery_concurrency),
            "LOADTEST_API_CPUS": str(step.api.cpus),
            "LOADTEST_API_MEMORY": step.api.memory,
            "LOADTEST_WORKER_CPUS": str(step.worker.cpus),
            "LOADTEST_WORKER_MEMORY": step.worker.memory,
            "LOADTEST_POSTGRES_CPUS": str(step.postgres.cpus),
            "LOADTEST_POSTGRES_MEMORY": step.postgres.memory,
            "LOADTEST_POSTGRES_MAX_CONNECTIONS": str(self.postgres.max_connections),
            "DATABASE_POOL_SIZE": str(self.database_pool.pool_size),
            "DATABASE_MAX_OVERFLOW": str(self.database_pool.max_overflow),
        }

    @classmethod
    def from_dict(cls, raw: dict) -> Profile:
        known = {
            "name",
            "description",
            "seed",
            "locust",
            "burn",
            "api",
            "worker",
            "postgres",
            "database_pool",
            "compute",
        }
        unknown = set(raw) - known
        if unknown:
            raise ValueError(f"Unknown profile keys: {', '.join(sorted(unknown))}")

        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("profile.name is required")
        description = raw.get("description", "")
        if not isinstance(description, str):
            raise ValueError("profile.description must be a string")

        seed = _require(raw, "seed")
        # Validate with the seeder's Scenario so a bad population fails here,
        # not halfway through a Docker seed run.
        if str(SEEDER_ROOT) not in sys.path:
            sys.path.insert(0, str(SEEDER_ROOT))
        from remitx_seeder.scenario import Scenario  # noqa: PLC0415

        Scenario.from_dict(seed)

        locust_raw = _require(raw, "locust")
        steps = locust_raw.get("steps")
        if (
            not isinstance(steps, list)
            or not steps
            or not all(
                isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in steps
            )
        ):
            raise ValueError("locust.steps must be a non-empty list of positive ints")
        step_seconds = locust_raw.get("step_seconds")
        spawn_rate = locust_raw.get("spawn_rate")
        if (
            not isinstance(step_seconds, int)
            or isinstance(step_seconds, bool)
            or step_seconds < 1
        ):
            raise ValueError("locust.step_seconds must be a positive int")
        if (
            not isinstance(spawn_rate, (int, float))
            or isinstance(spawn_rate, bool)
            or spawn_rate <= 0
        ):
            raise ValueError("locust.spawn_rate must be a positive number")

        burn_raw = _require(raw, "burn")
        try:
            p50 = float(burn_raw["p50_s"])
            p95 = float(burn_raw["p95_s"])
            failure_rate = float(burn_raw["failure_rate"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                "burn needs numeric p50_s, p95_s and failure_rate"
            ) from exc
        if not 0 < p50 <= p95:
            raise ValueError("burn needs 0 < p50_s <= p95_s")
        if not 0 <= failure_rate <= 1:
            raise ValueError("burn.failure_rate must be between 0 and 1")

        pool_raw = _require(raw, "database_pool")
        compute_raw = raw.get("compute")
        has_compute = isinstance(compute_raw, list) and len(compute_raw) > 0

        if has_compute:
            for key in ("api", "worker"):
                if key in raw:
                    raise ValueError(
                        f"profile.{key} is not used when compute is set; put "
                        f"{key} on each compute step instead"
                    )
            postgres_raw = raw.get("postgres")
            if not isinstance(postgres_raw, dict):
                raise ValueError(
                    "profile.postgres must be an object with max_connections "
                    "when compute is set (cpus/memory live on each step)"
                )
            if "cpus" in postgres_raw or "memory" in postgres_raw:
                raise ValueError(
                    "profile.postgres cpus/memory are not used when compute is "
                    "set; put them on each compute step"
                )
            try:
                max_connections = int(postgres_raw["max_connections"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    "postgres.max_connections is required when compute is set"
                ) from exc
            compute = _parse_compute(compute_raw)
            api = compute[0].api
            worker = compute[0].worker
            postgres = PostgresLimits(
                cpus=compute[0].postgres.cpus,
                memory=compute[0].postgres.memory,
                max_connections=max_connections,
            )
        else:
            api = _parse_api(_require(raw, "api"), label="api")
            worker = _parse_worker(_require(raw, "worker"), label="worker")
            postgres_raw = _require(raw, "postgres")
            try:
                postgres_cpus = float(postgres_raw["cpus"])
                max_connections = int(postgres_raw["max_connections"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("postgres needs cpus and max_connections") from exc
            if postgres_cpus <= 0:
                raise ValueError("postgres.cpus must be positive")
            postgres = PostgresLimits(
                cpus=postgres_cpus,
                memory=_memory(postgres_raw.get("memory"), "postgres.memory"),
                max_connections=max_connections,
            )
            compute = _parse_compute(compute_raw)

        try:
            pool_size = int(pool_raw["pool_size"])
            max_overflow = int(pool_raw["max_overflow"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("database_pool needs pool_size and max_overflow") from exc
        if max_connections < 1:
            raise ValueError("postgres.max_connections must be >= 1")
        if pool_size < 1:
            raise ValueError("database_pool.pool_size must be >= 1")
        if max_overflow < 0:
            raise ValueError("database_pool.max_overflow must be >= 0")
        per_process = pool_size + max_overflow
        # Neon reserves ~7 slots for the superuser. API + two Celery children
        # (concurrency 2) share the rest — load tests should fill that budget.
        processes = 3
        usable = max(1, max_connections - 7)
        if per_process * processes > usable:
            raise ValueError(
                f"database_pool ({per_process}/process × {processes} processes) "
                f"exceeds usable Neon slots ({usable} = max_connections "
                f"{max_connections} − 7 reserved)"
            )

        return cls(
            name=name.strip(),
            description=description,
            seed=seed,
            locust=LocustShape(
                steps=list(steps),
                step_seconds=step_seconds,
                spawn_rate=float(spawn_rate),
            ),
            burn=Burn(p50_s=p50, p95_s=p95, failure_rate=failure_rate),
            api=api,
            worker=worker,
            postgres=postgres,
            database_pool=DatabasePool(pool_size=pool_size, max_overflow=max_overflow),
            compute=compute,
        )


def _parse_service(raw: dict, *, label: str) -> ServiceLimits:
    try:
        cpus = float(raw["cpus"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} needs numeric cpus") from exc
    if cpus <= 0:
        raise ValueError(f"{label}.cpus must be positive")
    return ServiceLimits(
        cpus=cpus, memory=_memory(raw.get("memory"), f"{label}.memory")
    )


def _parse_api(raw: dict, *, label: str) -> ServiceLimits:
    return _parse_service(raw, label=label)


def _parse_worker(raw: dict, *, label: str) -> WorkerLimits:
    try:
        cpus = float(raw["cpus"])
        celery = int(raw["celery_concurrency"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} needs numeric cpus and celery_concurrency") from exc
    if cpus <= 0:
        raise ValueError(f"{label}.cpus must be positive")
    if celery < 1:
        raise ValueError(f"{label}.celery_concurrency must be >= 1")
    return WorkerLimits(
        cpus=cpus,
        memory=_memory(raw.get("memory"), f"{label}.memory"),
        celery_concurrency=celery,
    )


def _parse_compute(raw: object) -> tuple[ComputeStep, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("compute must be a list")
    if not raw:
        return ()

    steps: list[ComputeStep] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"compute[{index}] must be an object")
        name = entry.get("name")
        if not isinstance(name, str) or not _COMPUTE_NAME.match(name):
            raise ValueError(
                f"compute[{index}].name must be a slug like 'small' "
                f"(lowercase letters, digits, hyphens)"
            )
        if name in seen:
            raise ValueError(f"compute names must be unique; duplicate {name!r}")
        seen.add(name)

        unknown = set(entry) - {"name", "api", "worker", "postgres"}
        if unknown:
            raise ValueError(
                f"compute[{index}] unknown keys: {', '.join(sorted(unknown))}"
            )

        for field in ("api", "worker", "postgres"):
            if field not in entry or not isinstance(entry[field], dict):
                raise ValueError(
                    f"compute[{index}].{field} is required "
                    "(api, worker and postgres each need cpus + memory)"
                )

        api = _parse_api(entry["api"], label=f"compute[{index}].api")
        worker = _parse_worker(entry["worker"], label=f"compute[{index}].worker")
        postgres = _parse_service(entry["postgres"], label=f"compute[{index}].postgres")
        steps.append(ComputeStep(name=name, api=api, worker=worker, postgres=postgres))
    return tuple(steps)


def _require(raw: dict, key: str) -> dict:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"profile.{key} must be an object")
    return value


def _memory(value: object, label: str) -> str:
    if not isinstance(value, str) or not _MEMORY.match(value):
        raise ValueError(f"{label} must look like '512m' or '1g', not {value!r}")
    return value


def list_profiles() -> list[str]:
    return sorted(path.stem for path in PROFILES_DIR.glob("*.json"))


def profile_path(name: str) -> Path:
    path = PROFILES_DIR / f"{name}.json"
    if not path.is_file():
        known = ", ".join(list_profiles()) or "(none)"
        raise FileNotFoundError(f"Unknown load-test profile {name!r}; have: {known}")
    return path


def load_profile(name: str) -> Profile:
    return Profile.from_dict(json.loads(profile_path(name).read_text()))


def apply(name: str, *, write_seed: Path | None, print_exports: bool) -> Profile:
    profile = load_profile(name)
    if write_seed is not None:
        write_seed.parent.mkdir(parents=True, exist_ok=True)
        write_seed.write_text(json.dumps(profile.seed, indent=2) + "\n")
    if print_exports:
        for key, value in profile.exports().items():
            print(f"{key}={value}")
    return profile


def print_compute_steps(name: str) -> None:
    """JSON array of effective compute steps for run.sh to loop over."""
    profile = load_profile(name)
    print(json.dumps([step.to_dict() for step in profile.compute_steps()]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    list_p = sub.add_parser("list", help="List committed profiles")
    list_p.set_defaults(func=lambda _: print("\n".join(list_profiles()) or "(none)"))

    apply_p = sub.add_parser(
        "apply", help="Validate a profile; optionally write seed + exports"
    )
    apply_p.add_argument("name")
    apply_p.add_argument("--write-seed", type=Path, default=None)
    apply_p.add_argument(
        "--exports",
        action="store_true",
        help="Print KEY=value lines for the shell to source",
    )
    apply_p.set_defaults(
        func=lambda args: apply(
            args.name, write_seed=args.write_seed, print_exports=args.exports
        )
    )

    compute_p = sub.add_parser(
        "compute-steps",
        help="Print the effective compute sweep as JSON (for run.sh)",
    )
    compute_p.add_argument("name")
    compute_p.set_defaults(func=lambda args: print_compute_steps(args.name))

    exports_p = sub.add_parser(
        "exports-for",
        help="Print KEY=value exports for one compute step name",
    )
    exports_p.add_argument("name")
    exports_p.add_argument("compute_name")
    exports_p.set_defaults(
        func=lambda args: _print_exports_for(args.name, args.compute_name)
    )

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (FileNotFoundError, ValueError, json.JSONDecodeError, KeyError) as exc:
        print(f"profile: {exc}", file=sys.stderr)
        return 1
    return 0


def _print_exports_for(profile_name: str, compute_name: str) -> None:
    profile = load_profile(profile_name)
    for step in profile.compute_steps():
        if step.name == compute_name:
            for key, value in profile.exports(compute=step).items():
                print(f"{key}={value}")
            return
    known = ", ".join(s.name for s in profile.compute_steps())
    raise ValueError(f"Unknown compute step {compute_name!r}; have: {known}")


if __name__ == "__main__":
    raise SystemExit(main())
