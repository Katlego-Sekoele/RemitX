import pytest
from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.user import User
from remitx_api.repositories.user_repository import UserRepository
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


def test_get_by_clerk_id_returns_none_when_absent(app_context):
    assert UserRepository().get_by_clerk_id("user_missing") is None


def test_first_call_inserts_the_user(app_context):
    user = UserController().ensure_provisioned(
        "user_new", lambda: "new@example.com", lambda: "Sian"
    )

    assert user.clerk_user_id == "user_new"
    assert user.email == "new@example.com"
    assert user.first_name == "Sian"
    assert user.base_reference == "sian1"
    assert UserRepository().get_by_clerk_id("user_new") is not None


def test_base_reference_disambiguates_same_first_name(app_context):
    first = UserController().ensure_provisioned(
        "user_sian_a", lambda: "a@example.com", lambda: "Sian"
    )
    second = UserController().ensure_provisioned(
        "user_sian_b", lambda: "b@example.com", lambda: "Sian"
    )

    assert first.base_reference == "sian1"
    assert second.base_reference == "sian2"


def test_base_reference_falls_back_when_no_first_name(app_context):
    user = UserController().ensure_provisioned(
        "user_noname", lambda: "noname@example.com", lambda: None
    )

    assert user.base_reference == "user1"


def test_email_resolver_runs_only_on_insert(app_context):
    """Returning users must not trigger a Clerk API call."""
    calls = {"n": 0}

    def resolve():
        calls["n"] += 1
        return "once@example.com"

    controller = UserController()
    controller.ensure_provisioned("user_once", resolve, lambda: "Once")
    controller.ensure_provisioned("user_once", resolve, lambda: "Once")

    assert calls["n"] == 1


def test_repeat_call_is_idempotent(app_context):
    controller = UserController()
    first = controller.ensure_provisioned(
        "user_same", lambda: "same@example.com", lambda: "Same"
    )
    second = controller.ensure_provisioned(
        "user_same", lambda: "same@example.com", lambda: "Same"
    )

    assert first.id == second.id
    rows = db.session.scalars(
        select(User).where(User.clerk_user_id == "user_same")
    ).all()
    assert len(rows) == 1


def test_lost_insert_race_returns_the_winning_row(app_context, monkeypatch):
    """Two concurrent first requests: the loser must get the winner's row.

    Naively racing two calls after the winner has already committed doesn't
    exercise anything: the loser's own existence check would just find the
    committed row and return early, without ever reaching `add`. A real
    race has both requests pass that check *before* either commit, so this
    simulates that ordering directly: the loser's first existence check is
    forced to miss (as it would if it ran before the winner's commit was
    visible), its `add` is forced to raise IntegrityError (as the unique
    constraint would when the database rejects the second insert), and only
    its second existence check — the one in the except block — is allowed to
    see the real, already-committed winner row.
    """
    controller = UserController()
    winner = controller.ensure_provisioned(
        "user_race", lambda: "race@example.com", lambda: "Race"
    )

    original_get_by_clerk_id = UserRepository.get_by_clerk_id
    lookups = {"n": 0}

    def racy_lookup(self, clerk_user_id):
        lookups["n"] += 1
        if lookups["n"] == 1:
            return None
        return original_get_by_clerk_id(self, clerk_user_id)

    def failing_add(self, entity):
        raise IntegrityError("duplicate key", None, Exception())

    monkeypatch.setattr(UserRepository, "get_by_clerk_id", racy_lookup)
    monkeypatch.setattr(UserRepository, "add", failing_add)

    loser = UserController().ensure_provisioned(
        "user_race", lambda: "race@example.com", lambda: "Race"
    )
    assert loser.id == winner.id
    # Confirms the except branch actually ran: one miss (the loser's initial
    # check) plus one hit (the post-rollback re-fetch that found the winner).
    assert lookups["n"] == 2


def test_race_reraises_when_no_row_appears(app_context, monkeypatch):
    """An IntegrityError that is not a lost race must not be swallowed."""

    def always_fails(self, entity):
        raise IntegrityError("some other constraint", None, Exception())

    monkeypatch.setattr(UserRepository, "add", always_fails)

    with pytest.raises(IntegrityError):
        UserController().ensure_provisioned("user_broken", lambda: None, lambda: None)
