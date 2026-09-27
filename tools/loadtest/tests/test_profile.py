"""Load-test profiles: one JSON owns population + Locust shape + limits."""

import json
from pathlib import Path

import pytest

from loadtest_profile import Profile, apply, list_profiles, load_profile

PROFILES = Path(__file__).resolve().parents[1] / "profiles"

_FULL_STEP = {
    "api": {"cpus": 0.1, "memory": "512m"},
    "worker": {"cpus": 0.1, "memory": "512m", "celery_concurrency": 2},
    "postgres": {"cpus": 0.5, "memory": "2g"},
}


def test_committed_profiles_load():
    assert "default" in list_profiles()
    for name in list_profiles():
        load_profile(name)


def test_default_seed_is_a_funded_database_only_population():
    """What Locust acts as: many verified senders, no Clerk users, no live
    XRPL settlements, and a payout operator for cash-out."""
    seed = load_profile("default").seed
    assert seed["clerk_user_cap"] == 0
    assert seed["senders"] >= 2000
    assert seed["live_settlements"] == 0
    assert seed["money"]["dormant_rate"] == 0
    assert seed["money"]["reference_typo_rate"] == 0
    assert seed["ensure_every_path"] is False
    assert seed["staff"]["payout_operator"] >= 1
    assert seed["staff"]["compliance_officer"] >= 1
    assert seed["staff"]["treasury_operator"] >= 1


def test_apply_writes_seed_and_exports(tmp_path):
    seed_path = tmp_path / "seed.json"
    profile = apply("default", write_seed=seed_path, print_exports=False)
    written = json.loads(seed_path.read_text())
    assert written == profile.seed
    exports = profile.exports()
    assert exports["LOADTEST_STEPS"] == "10,25,50,100,250,500,1000"
    assert exports["LOADTEST_API_CPUS"] == "0.1"
    assert exports["LOADTEST_API_MEMORY"] == "512m"
    assert exports["LOADTEST_POSTGRES_MAX_CONNECTIONS"] == "839"
    assert exports["DATABASE_POOL_SIZE"] == "100"
    assert exports["DATABASE_MAX_OVERFLOW"] == "177"
    # Fill Neon Free usable slots (839 − 7 reserved) across API + 2 Celery kids.
    per_process = int(exports["DATABASE_POOL_SIZE"]) + int(
        exports["DATABASE_MAX_OVERFLOW"]
    )
    assert per_process * 3 == 831  # floor(832 / 3) × 3
    assert float(exports["LOADTEST_BURN_P50_S"]) == profile.burn.p50_s


def test_bad_locust_steps_are_refused():
    raw = json.loads((PROFILES / "default.json").read_text())
    raw["locust"]["steps"] = []
    with pytest.raises(ValueError, match="locust.steps"):
        Profile.from_dict(raw)


def test_pool_must_fit_under_postgres_max_connections():
    raw = json.loads((PROFILES / "default.json").read_text())
    raw["database_pool"] = {"pool_size": 400, "max_overflow": 400}
    with pytest.raises(ValueError, match="max_connections"):
        Profile.from_dict(raw)


def test_bad_seed_review_delay_is_refused():
    raw = json.loads((PROFILES / "default.json").read_text())
    raw["seed"]["kyc"]["review_delay_hours"] = [1, 24, 36, 48]
    with pytest.raises(ValueError, match="review_delay_hours"):
        Profile.from_dict(raw)


def test_default_has_one_implicit_compute_step():
    profile = load_profile("default")
    assert profile.compute == ()
    steps = profile.compute_steps()
    assert len(steps) == 1
    assert steps[0].name == "default"
    assert steps[0].api.cpus == 0.1
    assert steps[0].worker.cpus == 0.1
    assert steps[0].postgres.cpus == 2.0


def test_compute_sweep_has_three_scaled_tiers():
    profile = load_profile("compute-sweep")
    raw = json.loads((PROFILES / "compute-sweep.json").read_text())
    assert "api" not in raw
    assert "worker" not in raw
    assert set(raw["postgres"]) == {"max_connections"}
    steps = profile.compute_steps()
    assert [s.name for s in steps] == ["small", "medium", "large"]
    assert [s.api.cpus for s in steps] == [0.1, 1.0, 2.0]
    assert [s.api.memory for s in steps] == ["512m", "1g", "2g"]
    assert [s.worker.cpus for s in steps] == [0.1, 1.0, 2.0]
    assert [s.worker.memory for s in steps] == ["512m", "1g", "2g"]
    assert [s.postgres.cpus for s in steps] == [0.5, 1.0, 2.0]
    assert [s.postgres.memory for s in steps] == ["2g", "4g", "8g"]
    exports = profile.exports(compute=steps[1])
    assert exports["LOADTEST_API_CPUS"] == "1.0"
    assert exports["LOADTEST_WORKER_CPUS"] == "1.0"
    assert exports["LOADTEST_POSTGRES_CPUS"] == "1.0"
    assert exports["LOADTEST_POSTGRES_MEMORY"] == "4g"
    assert exports["LOADTEST_POSTGRES_MAX_CONNECTIONS"] == "839"


def test_compute_rejects_top_level_api_and_worker():
    raw = json.loads((PROFILES / "compute-sweep.json").read_text())
    raw["api"] = {"cpus": 0.1, "memory": "512m"}
    with pytest.raises(ValueError, match="profile.api is not used when compute"):
        Profile.from_dict(raw)
    del raw["api"]
    raw["worker"] = {"cpus": 0.1, "memory": "512m", "celery_concurrency": 2}
    with pytest.raises(ValueError, match="profile.worker is not used when compute"):
        Profile.from_dict(raw)


def test_compute_rejects_top_level_postgres_cpus():
    raw = json.loads((PROFILES / "compute-sweep.json").read_text())
    raw["postgres"] = {"max_connections": 839, "cpus": 2, "memory": "8g"}
    with pytest.raises(ValueError, match="postgres cpus/memory are not used"):
        Profile.from_dict(raw)


def test_compute_step_requires_api_worker_postgres():
    raw = json.loads((PROFILES / "compute-sweep.json").read_text())
    raw["compute"] = [{"name": "only-name"}]
    with pytest.raises(ValueError, match="compute\\[0\\].api is required"):
        Profile.from_dict(raw)


def test_compute_names_must_be_unique_slugs():
    raw = json.loads((PROFILES / "compute-sweep.json").read_text())
    raw["compute"] = [
        {"name": "a", **_FULL_STEP},
        {"name": "a", **_FULL_STEP},
    ]
    with pytest.raises(ValueError, match="unique"):
        Profile.from_dict(raw)

    raw["compute"] = [{"name": "Bad_Name", **_FULL_STEP}]
    with pytest.raises(ValueError, match="slug"):
        Profile.from_dict(raw)


def test_empty_compute_list_is_one_default_step():
    raw = json.loads((PROFILES / "default.json").read_text())
    raw["compute"] = []
    profile = Profile.from_dict(raw)
    assert profile.compute_steps()[0].name == "default"
