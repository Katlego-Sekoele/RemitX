"""Role administration: grant, revoke, and the rules gating cannot express.

Nothing here fakes a permission. Every caller holds real ``user_roles`` rows
and the routes resolve them out of the database on each request, the same way
production does — see tests/rbac_helpers.py.
"""

import uuid

from remitx_api.auth.dependencies import get_current_user
from remitx_api.extensions import db
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.rbac_seed import (
    precompute_permission_id_given_permission_code,
    precompute_role_id_given_role_name,
)
from remitx_api.models.orm.toxic_combination import ToxicCombination
from remitx_api.models.orm.user_role import UserRole
from remitx_api.repositories.role_repository import RoleRepository
from remitx_api.repositories.user_repository import UserRepository
from sqlalchemy import select
from tests.rbac_helpers import grant_role, make_user, rbac_client

REASON = "Joining the compliance rota this quarter."


def _grant(client, user_id, role, **extra):
    return client.post(
        f"/admin/users/{user_id}/roles",
        json={"role": role, "reason": REASON, **extra},
    )


def _revoke(client, user_id, role, reason=REASON):
    return client.request(
        "DELETE",
        f"/admin/users/{user_id}/roles/{role}",
        json={"reason": reason},
    )


def _active_rows(user_id: uuid.UUID) -> list[UserRole]:
    return list(
        db.session.scalars(select(UserRole).where(UserRole.user_id == user_id)).all()
    )


def test_grant_records_actor_reason_and_takes_effect():
    admin = make_user("admin")
    with rbac_client(admin, roles=("iam_admin",)) as client:
        target = UserRepository().save(make_user("target"))

        response = _grant(client, target.id, "support_agent")

        assert response.status_code == 200
        payload = response.json()
        assert payload["created"] is True
        grant = payload["grant"]
        assert grant["role"] == "support_agent"
        assert grant["display_name"] == "Support Agent"
        assert grant["grant_reason"] == REASON
        assert grant["granted_by"] == str(admin.id)
        assert grant["self_granted"] is False
        assert grant["active"] is True
        assert grant["revoked_at"] is None


def test_grant_requires_a_reason():
    admin = make_user("admin")
    with rbac_client(admin, roles=("iam_admin",)) as client:
        target = UserRepository().save(make_user("target"))

        missing = client.post(
            f"/admin/users/{target.id}/roles",
            json={"role": "support_agent"},
        )
        too_short = client.post(
            f"/admin/users/{target.id}/roles",
            json={"role": "support_agent", "reason": "n/a"},
        )

        assert missing.status_code == 422
        assert too_short.status_code == 422
        assert _active_rows(target.id) == []


def test_revoke_requires_a_reason():
    admin = make_user("admin")
    with rbac_client(admin, roles=("iam_admin",)) as client:
        target = UserRepository().save(make_user("target"))
        grant_role(target.id, "support_agent")

        response = client.request(
            "DELETE",
            f"/admin/users/{target.id}/roles/support_agent",
            json={},
        )

        assert response.status_code == 422


def test_granting_a_held_role_returns_the_existing_grant():
    admin = make_user("admin")
    with rbac_client(admin, roles=("iam_admin",)) as client:
        target = UserRepository().save(make_user("target"))

        first = _grant(client, target.id, "support_agent").json()
        second = _grant(client, target.id, "support_agent").json()

        assert first["created"] is True
        assert second["created"] is False
        assert second["grant"]["user_role_id"] == first["grant"]["user_role_id"]
        assert len(_active_rows(target.id)) == 1


def test_revoke_stamps_the_row_and_never_deletes_it():
    admin = make_user("admin")
    with rbac_client(admin, roles=("iam_admin",)) as client:
        target = UserRepository().save(make_user("target"))
        _grant(client, target.id, "support_agent")

        response = _revoke(client, target.id, "support_agent", "Left the team.")

        assert response.status_code == 200
        revoked = response.json()
        assert revoked["active"] is False
        assert revoked["revoked_at"] is not None
        assert revoked["revoked_by"] == str(admin.id)
        assert revoked["revoke_reason"] == "Left the team."

        rows = _active_rows(target.id)
        assert len(rows) == 1, "revoking must not delete the grant"
        assert rows[0].revoked_at is not None
        assert rows[0].grant_reason == REASON


def test_regranting_after_a_revoke_keeps_both_rows():
    admin = make_user("admin")
    with rbac_client(admin, roles=("iam_admin",)) as client:
        target = UserRepository().save(make_user("target"))
        _grant(client, target.id, "support_agent")
        _revoke(client, target.id, "support_agent", "Moved to another team.")

        again = _grant(client, target.id, "support_agent")

        assert again.status_code == 200
        assert again.json()["created"] is True
        assert len(_active_rows(target.id)) == 2

        history = client.get(f"/admin/users/{target.id}/roles").json()["roles"]
        assert [item["active"] for item in history].count(True) == 1
        assert [item["active"] for item in history].count(False) == 1


def test_revoke_of_a_role_the_user_does_not_hold_is_404():
    admin = make_user("admin")
    with rbac_client(admin, roles=("iam_admin",)) as client:
        target = UserRepository().save(make_user("target"))

        response = _revoke(client, target.id, "support_agent")

        assert response.status_code == 404


def test_unknown_role_and_unknown_user_are_404():
    admin = make_user("admin")
    with rbac_client(admin, roles=("iam_admin",)) as client:
        target = UserRepository().save(make_user("target"))

        unknown_role = _grant(client, target.id, "wizard")
        unknown_user = _grant(client, uuid.uuid4(), "support_agent")

        assert unknown_role.status_code == 404
        assert unknown_user.status_code == 404


def test_customer_is_implicit_and_cannot_be_granted():
    admin = make_user("admin")
    with rbac_client(admin, roles=("iam_admin",)) as client:
        target = UserRepository().save(make_user("target"))

        response = _grant(client, target.id, "customer")

        assert response.status_code == 400
        assert "cannot be granted" in response.json()["detail"]
        assert _active_rows(target.id) == []


def test_self_grant_is_allowed_and_flagged():
    admin = make_user("admin")
    with rbac_client(admin, roles=("iam_admin",)) as client:
        response = _grant(client, admin.id, "compliance_officer")

        assert response.status_code == 200
        assert response.json()["grant"]["self_granted"] is True


def test_the_last_iam_admin_cannot_be_revoked():
    admin = make_user("admin")
    with rbac_client(admin, roles=("iam_admin",)) as client:
        response = _revoke(client, admin.id, "iam_admin")

        assert response.status_code == 409
        assert "last active iam_admin" in response.json()["detail"]

        rows = _active_rows(admin.id)
        assert rows[0].revoked_at is None


def test_a_second_iam_admin_makes_the_first_revocable():
    admin = make_user("admin")
    with rbac_client(admin, roles=("iam_admin",)) as client:
        successor = UserRepository().save(make_user("successor"))
        _grant(client, successor.id, "iam_admin")

        response = _revoke(client, admin.id, "iam_admin", "Handing over IAM.")

        assert response.status_code == 200
        assert response.json()["active"] is False


def test_toxic_combination_is_warned_about_and_acceptance_recorded():
    admin = make_user("admin")
    with rbac_client(admin, roles=("iam_admin",)) as client:
        target = UserRepository().save(make_user("target"))
        _grant(client, target.id, "treasury_operator")

        response = _grant(
            client,
            target.id,
            "payout_operator",
            toxic_combination_acknowledged=True,
        )

        assert response.status_code == 200
        payload = response.json()
        combinations = payload["toxic_combinations"]
        assert len(combinations) == 1
        assert set(combinations[0]["permissions"]) == {
            PermissionCode.CASHIN_CONFIRM.value,
            PermissionCode.CASHOUT_COMPLETE.value,
        }
        assert payload["grant"]["toxic_combination_acknowledged"] is True


def test_toxic_combination_acknowledgement_without_a_warning_is_not_recorded():
    """The column says a warning was accepted, so it cannot be set by a
    caller who was never shown one."""
    admin = make_user("admin")
    with rbac_client(admin, roles=("iam_admin",)) as client:
        target = UserRepository().save(make_user("target"))

        response = _grant(
            client,
            target.id,
            "support_agent",
            toxic_combination_acknowledged=True,
        )

        assert response.json()["toxic_combinations"] == []
        assert response.json()["grant"]["toxic_combination_acknowledged"] is False


def test_toxic_combination_catalogue_is_served_from_the_server():
    with rbac_client(make_user("admin"), roles=("iam_admin",)) as client:
        response = client.get("/admin/roles/toxic-combinations")

    assert response.status_code == 200
    combinations = response.json()
    assert len(combinations) == 2
    for combination in combinations:
        assert len(combination["permissions"]) == 2
        assert combination["explanation"]


def test_user_access_lists_effective_permissions_and_history():
    admin = make_user("admin")
    with rbac_client(admin, roles=("iam_admin",)) as client:
        target = UserRepository().save(make_user("target"))
        _grant(client, target.id, "support_agent")

        response = client.get(f"/admin/users/{target.id}/roles")

    assert response.status_code == 200
    payload = response.json()
    assert payload["email"] == "target@example.com"
    assert PermissionCode.TRANSACTION_READ_ANY.value in payload["permissions"]
    assert PermissionCode.ROLE_GRANT.value not in payload["permissions"]
    assert [item["role"] for item in payload["roles"]] == ["support_agent"]


def test_admin_list_covers_role_holders_and_leads_with_self_grants():
    admin = make_user("admin")
    with rbac_client(admin, roles=("iam_admin",)) as client:
        colleague = UserRepository().save(make_user("colleague"))
        _grant(client, colleague.id, "support_agent")
        # A customer with no roles is not an admin and must not appear.
        UserRepository().save(make_user("customer"))
        _grant(client, admin.id, "auditor")

        response = client.get("/admin/users/admins")

    assert response.status_code == 200
    admins = response.json()
    assert {member["email"] for member in admins} == {
        "admin@example.com",
        "colleague@example.com",
    }
    assert admins[0]["email"] == "admin@example.com"
    assert admins[0]["has_self_grant"] is True
    assert sorted(role["role"] for role in admins[0]["roles"]) == [
        "auditor",
        "iam_admin",
    ]


def test_user_search_matches_on_email_fragment():
    admin = make_user("admin")
    with rbac_client(admin, roles=("iam_admin",)) as client:
        UserRepository().save(make_user("colleague"))

        hit = client.get("/admin/users/search", params={"email": "colleagu"})
        miss = client.get("/admin/users/search", params={"email": "nobody"})

    assert hit.status_code == 200
    assert [item["email"] for item in hit.json()] == ["colleague@example.com"]
    assert miss.json() == []


def test_grant_needs_role_grant_and_revoke_needs_role_revoke():
    """`role:read` gets the reader in; it does not get them a grant."""
    reader = make_user("reader")
    with rbac_client(reader, permissions=(PermissionCode.ROLE_READ,)) as client:
        target = UserRepository().save(make_user("target"))
        grant_role(target.id, "support_agent")

        assert client.get(f"/admin/users/{target.id}/roles").status_code == 200
        assert _grant(client, target.id, "auditor").status_code == 403
        assert _revoke(client, target.id, "support_agent").status_code == 403


def test_user_search_needs_user_read_on_top_of_role_read():
    reader = make_user("reader")
    with rbac_client(reader, permissions=(PermissionCode.ROLE_READ,)) as client:
        response = client.get("/admin/users/search", params={"email": "anyone"})

    assert response.status_code == 403
    assert response.json()["detail"] == (
        f"Missing permission: {PermissionCode.USER_READ.value}"
    )


def test_revoking_through_the_api_takes_effect_on_the_next_request():
    """Permissions resolve per request, so a revoke lands immediately — no
    session to expire, no cache to wait out."""
    admin = make_user("admin")
    holder = make_user("holder")

    with rbac_client(admin, roles=("iam_admin",)) as client:
        UserRepository().save(holder)
        grant_role(holder.id, "treasury_operator")

        # One app, two callers: the holder works while the admin revokes,
        # which is the sequence the guarantee is about.
        def acting_as(user):
            client.app.dependency_overrides[get_current_user] = lambda: user

        acting_as(holder)
        assert client.get("/admin/deposits/pending").status_code == 200

        acting_as(admin)
        revoked = _revoke(
            client,
            holder.id,
            "treasury_operator",
            "Rotated off treasury.",
        )
        assert revoked.status_code == 200

        acting_as(holder)
        assert client.get("/admin/deposits/pending").status_code == 403


def test_seeded_role_ids_are_what_the_api_grants():
    """Guards the deterministic uuid5 seeding the migration relies on: a
    grant made through the API has to point at the same row the catalogue
    migration inserted, not a lookalike."""
    admin = make_user("admin")
    with rbac_client(admin, roles=("iam_admin",)) as client:
        target = UserRepository().save(make_user("target"))
        _grant(client, target.id, "auditor")

        rows = _active_rows(target.id)

    assert rows[0].role_id == precompute_role_id_given_role_name("auditor")


def test_grantability_is_read_from_the_catalogue_not_a_role_name():
    """The rule lives in ``roles.is_grantable``, so flipping the row flips the
    answer — no deploy, and no role name to drift inside a controller."""
    admin = make_user("admin")
    with rbac_client(admin, roles=("iam_admin",)) as client:
        target = UserRepository().save(make_user("target"))
        assert _grant(client, target.id, "customer").status_code == 400

        customer_role = RoleRepository().get_by_name("customer")
        customer_role.is_grantable = True
        support_role = RoleRepository().get_by_name("support_agent")
        support_role.is_grantable = False
        db.session.commit()

        assert _grant(client, target.id, "customer").status_code == 200
        assert _grant(client, target.id, "support_agent").status_code == 400


def test_last_holder_protection_is_read_from_the_catalogue():
    """Same for the 409: ``roles.protect_last_holder`` decides it, not the
    string "iam_admin"."""
    admin = make_user("admin")
    with rbac_client(admin, roles=("iam_admin",)) as client:
        assert _revoke(client, admin.id, "iam_admin").status_code == 409

        RoleRepository().get_by_name("iam_admin").protect_last_holder = False
        db.session.commit()

        assert _revoke(client, admin.id, "iam_admin").status_code == 200


def test_a_toxic_combination_added_to_the_database_is_warned_about():
    """A new separation-of-duties rule is an INSERT, not a release."""
    admin = make_user("admin")
    with rbac_client(admin, roles=("iam_admin",)) as client:
        target = UserRepository().save(make_user("target"))

        db.session.add(
            ToxicCombination(
                permission_a_id=precompute_permission_id_given_permission_code(
                    PermissionCode.TRANSACTION_READ_ANY
                ),
                permission_b_id=precompute_permission_id_given_permission_code(
                    PermissionCode.KYC_APPLICATION_READ
                ),
                explanation="Invented for this test, and never deployed.",
            )
        )
        db.session.commit()

        response = _grant(
            client,
            target.id,
            "support_agent",
            toxic_combination_acknowledged=True,
        )

    payload = response.json()
    assert [
        combination["explanation"] for combination in payload["toxic_combinations"]
    ] == ["Invented for this test, and never deployed."]
    assert payload["grant"]["toxic_combination_acknowledged"] is True


def test_toxic_combination_catalogue_reflects_the_database():
    admin = make_user("admin")
    with rbac_client(admin, roles=("iam_admin",)) as client:
        before = client.get("/admin/roles/toxic-combinations").json()

        db.session.query(ToxicCombination).delete()
        db.session.commit()

        after = client.get("/admin/roles/toxic-combinations").json()

    assert len(before) == 2
    assert after == []
