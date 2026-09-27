"""Build a graded load-test summary from Locust CSVs (HTTP vs SETTLE split)."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Plateau:
    users: int
    http_median_ms: float | None
    http_p95_ms: float | None
    http_rps: float
    http_requests: int
    http_failures: int
    settle_e2e_rps: float
    settle_e2e_n: int
    settle_e2e_failures: int
    chain_confirm_median_ms: float | None
    queue_wait_median_ms: float | None


@dataclass(frozen=True)
class EndpointStat:
    name: str
    median_ms: float
    average_ms: float
    requests: int
    failures: int


@dataclass(frozen=True)
class ComputeSummary:
    name: str
    api_cpus: float | None
    api_memory: str | None
    worker_cpus: float | None
    postgres_cpus: float | None
    plateaus: list[Plateau]
    endpoints_at_10: list[EndpointStat]
    http_fail_pct: float
    settle_fail_pct: float
    peak_http_rps: float
    settle_throughput_at_peak_users: float


@dataclass(frozen=True)
class RunSummary:
    profile_name: str
    description: str
    burn_p50_s: float
    burn_p95_s: float
    locust_steps: list[int]
    compute: list[ComputeSummary]
    bottleneck: str


def discover_compute_dirs(
    run_dir: Path, *, preferred_order: list[str] | None = None
) -> list[Path]:
    compute_root = run_dir / "compute"
    if compute_root.is_dir():
        dirs = [p for p in compute_root.iterdir() if p.is_dir() and _has_stats(p)]
        if dirs:
            if preferred_order:
                rank = {name: i for i, name in enumerate(preferred_order)}
                dirs.sort(key=lambda p: (rank.get(p.name, 10_000), p.name))
            else:
                dirs.sort(key=lambda p: p.name)
            return dirs
    if _has_stats(run_dir):
        return [run_dir]
    raise FileNotFoundError(f"No Locust stats under {run_dir}/compute/*/ or {run_dir}/")


def _has_stats(path: Path) -> bool:
    return (path / "stats_stats_history.csv").is_file()


def build_summary(run_dir: Path) -> RunSummary:
    profile_path = run_dir / "profile.json"
    profile = json.loads(profile_path.read_text()) if profile_path.is_file() else {}
    burn = profile.get("burn") or {}
    locust = profile.get("locust") or {}
    steps = list(locust.get("steps") or [])
    compute_list = [c for c in (profile.get("compute") or []) if isinstance(c, dict)]
    compute_meta = {
        c["name"]: c for c in compute_list if isinstance(c.get("name"), str)
    }
    preferred = [c["name"] for c in compute_list if isinstance(c.get("name"), str)]
    default_api = profile.get("api") or {}
    default_worker = profile.get("worker") or {}
    default_postgres = profile.get("postgres") or {}

    computes: list[ComputeSummary] = []
    for directory in discover_compute_dirs(run_dir, preferred_order=preferred):
        name = directory.name if directory != run_dir else "default"
        meta = compute_meta.get(name, {})
        api = meta.get("api") or default_api
        worker = meta.get("worker") or default_worker
        postgres = meta.get("postgres") or default_postgres
        plateaus = _plateaus_from_history(directory, steps)
        endpoints = _endpoints_at_users(directory, target_users=10)
        totals = _final_totals(directory)
        peak_users = max((p.users for p in plateaus), default=0)
        peak = next((p for p in plateaus if p.users == peak_users), None)
        computes.append(
            ComputeSummary(
                name=name,
                api_cpus=_float_or_none(api.get("cpus")),
                api_memory=api.get("memory")
                if isinstance(api.get("memory"), str)
                else None,
                worker_cpus=_float_or_none(worker.get("cpus")),
                postgres_cpus=_float_or_none(postgres.get("cpus")),
                plateaus=plateaus,
                endpoints_at_10=endpoints,
                http_fail_pct=totals["http_fail_pct"],
                settle_fail_pct=totals["settle_fail_pct"],
                peak_http_rps=peak.http_rps if peak else 0.0,
                settle_throughput_at_peak_users=(peak.settle_e2e_rps if peak else 0.0),
            )
        )

    return RunSummary(
        profile_name=str(profile.get("name") or run_dir.name),
        description=str(profile.get("description") or ""),
        burn_p50_s=float(burn.get("p50_s") or 0),
        burn_p95_s=float(burn.get("p95_s") or 0),
        locust_steps=steps,
        compute=computes,
        bottleneck=_bottleneck_text(computes, float(burn.get("p50_s") or 0)),
    )


def summary_to_dict(summary: RunSummary) -> dict:
    return asdict(summary)


def _float_or_none(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _num(value: object) -> float | None:
    if value is None or value == "" or value == "N/A":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _plateaus_from_history(directory: Path, locust_steps: list[int]) -> list[Plateau]:
    history = list(csv.DictReader((directory / "stats_stats_history.csv").open()))
    # Last snapshot per user count (cumulative Locust totals stabilize at step end).
    by_users: dict[int, dict[str, dict]] = {}
    for row in history:
        users = int(float(row["User Count"] or 0))
        if users <= 0:
            continue
        by_users.setdefault(users, {})[row["Name"]] = row

    targets = locust_steps or sorted(by_users)
    plateaus: list[Plateau] = []
    for users in targets:
        # Prefer exact match; else nearest at-or-below recorded count.
        snapshot = by_users.get(users)
        if snapshot is None:
            candidates = [u for u in by_users if u <= users]
            if not candidates:
                continue
            snapshot = by_users[max(candidates)]
            users = max(candidates)

        http_rows = [
            r
            for name, r in snapshot.items()
            if name not in ("Aggregated",) and r.get("Type") != "SETTLE" and name
        ]
        settle_e2e = snapshot.get("end to end")
        chain = snapshot.get("chain + confirm")
        queue = snapshot.get("queue wait")

        http_n = sum(int(float(r.get("Total Request Count") or 0)) for r in http_rows)
        http_fail = sum(
            int(float(r.get("Total Failure Count") or 0)) for r in http_rows
        )
        http_rps = sum(_num(r.get("Requests/s")) or 0.0 for r in http_rows)
        medians = [
            (
                _num(r.get("Total Median Response Time")),
                int(float(r.get("Total Request Count") or 0)),
            )
            for r in http_rows
        ]
        http_median = _weighted_median_of_medians(medians)
        p95s = [
            (_num(r.get("95%")), int(float(r.get("Total Request Count") or 0)))
            for r in http_rows
        ]
        http_p95 = _weighted_median_of_medians(p95s)

        plateaus.append(
            Plateau(
                users=users,
                http_median_ms=http_median,
                http_p95_ms=http_p95,
                http_rps=http_rps,
                http_requests=http_n,
                http_failures=http_fail,
                settle_e2e_rps=_num(
                    settle_e2e.get("Requests/s") if settle_e2e else None
                )
                or 0.0,
                settle_e2e_n=int(
                    float(settle_e2e.get("Total Request Count") or 0)
                    if settle_e2e
                    else 0
                ),
                settle_e2e_failures=int(
                    float(settle_e2e.get("Total Failure Count") or 0)
                    if settle_e2e
                    else 0
                ),
                chain_confirm_median_ms=_num(
                    chain.get("Total Median Response Time") if chain else None
                ),
                queue_wait_median_ms=_num(
                    queue.get("Total Median Response Time") if queue else None
                ),
            )
        )
    return plateaus


def _weighted_median_of_medians(
    pairs: list[tuple[float | None, int]],
) -> float | None:
    usable = [(m, n) for m, n in pairs if m is not None and n > 0]
    if not usable:
        return None
    usable.sort(key=lambda p: p[0])
    total = sum(n for _, n in usable)
    cum = 0
    for median, n in usable:
        cum += n
        if cum >= total / 2:
            return median
    return usable[-1][0]


def _endpoints_at_users(directory: Path, *, target_users: int) -> list[EndpointStat]:
    history = list(csv.DictReader((directory / "stats_stats_history.csv").open()))
    last: dict[str, dict] = {}
    for row in history:
        if int(float(row["User Count"] or 0)) != target_users:
            continue
        if row.get("Type") == "SETTLE" or row["Name"] in ("", "Aggregated"):
            continue
        last[row["Name"]] = row
    stats = [
        EndpointStat(
            name=name,
            median_ms=_num(r.get("Total Median Response Time")) or 0.0,
            average_ms=_num(r.get("Total Average Response Time")) or 0.0,
            requests=int(float(r.get("Total Request Count") or 0)),
            failures=int(float(r.get("Total Failure Count") or 0)),
        )
        for name, r in last.items()
    ]
    stats.sort(key=lambda e: -e.median_ms)
    return stats[:5]


def _final_totals(directory: Path) -> dict[str, float]:
    stats_path = directory / "stats_stats.csv"
    if not stats_path.is_file():
        return {"http_fail_pct": 0.0, "settle_fail_pct": 0.0}
    http_n = http_f = settle_n = settle_f = 0
    for row in csv.DictReader(stats_path.open()):
        name = row.get("Name") or ""
        if name in ("", "Aggregated"):
            continue
        n = int(float(row.get("Request Count") or 0))
        f = int(float(row.get("Failure Count") or 0))
        if row.get("Type") == "SETTLE":
            if name == "end to end":
                settle_n, settle_f = n, f
            continue
        http_n += n
        http_f += f
    return {
        "http_fail_pct": (100.0 * http_f / http_n) if http_n else 0.0,
        "settle_fail_pct": (100.0 * settle_f / settle_n) if settle_n else 0.0,
    }


def _bottleneck_text(computes: list[ComputeSummary], burn_p50_s: float) -> str:
    if not computes:
        return "No compute results were found for this run."
    at_10 = []
    for c in computes:
        p = next(
            (x for x in c.plateaus if x.users == 10),
            c.plateaus[0] if c.plateaus else None,
        )
        if p and p.http_median_ms is not None:
            at_10.append((c, p))
    if len(at_10) >= 2:
        slow = max(at_10, key=lambda t: t[1].http_median_ms or 0)
        fast = min(at_10, key=lambda t: t[1].http_median_ms or 0)
        slow_ms = slow[1].http_median_ms or 0
        fast_ms = fast[1].http_median_ms or 0
        if slow_ms > 500 and fast_ms > 0 and slow_ms / fast_ms >= 5:
            return (
                f"At 10 concurrent users, HTTP median latency is "
                f"{slow_ms:.0f} ms on {slow[0].name} "
                f"(API {slow[0].api_cpus} CPU) versus {fast_ms:.0f} ms on "
                f"{fast[0].name} (API {fast[0].api_cpus} CPU). "
                f"That gap points to API CPU starvation under the smaller "
                f"compute cap, not Postgres or the settlement queue. "
                f"Calibrated RLUSD burn remains ~{burn_p50_s:.1f} s p50 on Testnet; "
                f"queue throughput follows worker capacity and burn delay."
            )
    first = at_10[0] if at_10 else None
    if first and (first[1].http_median_ms or 0) >= 1000:
        c, p = first
        return (
            f"HTTP median at 10 users is already {p.http_median_ms:.0f} ms on "
            f"{c.name} (API {c.api_cpus} CPU). Latency climbs further as Locust "
            f"steps up concurrent users while RPS stays low — the API process is "
            f"the saturation point. Calibrated RLUSD burn is ~{burn_p50_s:.1f} s p50."
        )
    if first:
        c, p = first
        return (
            f"Under {c.name} (API {c.api_cpus} CPU), HTTP median at 10 users is "
            f"{p.http_median_ms:.0f} ms with peak HTTP RPS "
            f"{c.peak_http_rps:.1f}. Settlement end-to-end rate at peak users is "
            f"{c.settle_throughput_at_peak_users:.2f}/s; RLUSD burn calibration "
            f"is {burn_p50_s:.1f} s p50. Watch how median and RPS move across "
            f"the Locust user steps for concurrency behaviour."
        )
    return "Insufficient plateau data to identify a bottleneck."
