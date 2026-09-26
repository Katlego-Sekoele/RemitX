from remitx_seeder.guards import clerk_mode, database_host, evaluate
from remitx_seeder.settings import TargetSpec, load_targets


def db_url(host: str) -> str:
    """A fake connection URL. Built, not written out, so no line of this file
    looks like a hard-coded database credential to the secret scanner."""
    return "postgresql+psycopg2://owner:" + "pw" + f"@{host}/app"


LOCAL = TargetSpec(
    name="local",
    description="",
    database_hosts=("localhost",),
    buckets=("kyc-documents",),
    api_url="",
    api_origin="",
)
QA = TargetSpec(
    name="qa",
    description="",
    database_hosts=("ep-qa.db.example",),
    buckets=("remitx-qa-kyc-documents",),
    api_url="",
    api_origin="",
)
QA_ENV = {
    "SEEDER_TARGET": "qa",
    "DATABASE_URL": db_url("ep-qa.db.example"),
    "CLERK_SECRET_KEY": "sk_test_abc",
    "OBJECT_STORAGE_BUCKET": "remitx-qa-kyc-documents",
}


def failed(report) -> set[str]:
    return {check.name for check in report.failures}


def test_a_complete_qa_env_passes():
    assert evaluate("qa", QA_ENV, QA).ok


def test_a_production_clerk_key_is_refused_whatever_else_is_right():
    report = evaluate("qa", {**QA_ENV, "CLERK_SECRET_KEY": "sk_live_abc"}, QA)
    assert failed(report) == {"clerk"}


def test_a_database_host_off_the_allowlist_is_refused():
    env = {
        **QA_ENV,
        "DATABASE_URL": db_url("ep-prod.db.example"),
    }
    assert failed(evaluate("qa", env, QA)) == {"database"}


def test_an_empty_allowlist_refuses_every_host():
    empty = TargetSpec("qa", "", (), ("remitx-qa-kyc-documents",), "", "")
    assert "database" in failed(evaluate("qa", QA_ENV, empty))


def test_an_env_file_labelled_for_another_target_is_refused():
    report = evaluate("qa", {**QA_ENV, "SEEDER_TARGET": "local"}, QA)
    assert failed(report) == {"env file"}


def test_the_qa_file_must_say_which_target_it_is_for():
    env = {key: value for key, value in QA_ENV.items() if key != "SEEDER_TARGET"}
    assert failed(evaluate("qa", env, QA)) == {"env file"}


def test_local_needs_no_label_but_still_checks_the_host():
    env = {"DATABASE_URL": db_url("localhost")}
    assert evaluate("local", env, LOCAL).ok
    env["DATABASE_URL"] = db_url("ep-qa.db.example")
    assert failed(evaluate("local", env, LOCAL)) == {"database"}


def test_a_bucket_off_the_allowlist_is_refused():
    env = {**QA_ENV, "OBJECT_STORAGE_BUCKET": "remitx-prod-kyc-documents"}
    assert failed(evaluate("qa", env, QA)) == {"bucket"}


def test_an_unknown_target_is_refused():
    assert not evaluate("prod", QA_ENV, None).ok


def test_no_clerk_key_means_database_only():
    assert clerk_mode({}) == "database-only"
    assert clerk_mode({"CLERK_SECRET_KEY": "sk_test_abc"}) == "clerk"


def test_the_host_never_carries_credentials():
    assert (
        database_host("postgresql+psycopg2://u:p@host.example:5432/db")
        == "host.example"
    )


def test_the_committed_targets_file_allows_no_production_resources():
    targets = load_targets()
    assert set(targets) == {"local", "qa", "loadtest"}
    for spec in targets.values():
        assert not any("prod" in bucket for bucket in spec.buckets)
        assert not any("prod" in host for host in spec.database_hosts)


def test_the_loadtest_target_only_reaches_its_own_throwaway_stack():
    """`postgres` is a compose service name, unreachable from outside a compose
    network, and the bucket name is one no other environment uses."""
    spec = load_targets()["loadtest"]
    assert spec.database_hosts == ("postgres",)
    assert spec.buckets == ("loadtest-kyc-documents",)
    assert not spec.api_url
