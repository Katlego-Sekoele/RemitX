import re
import uuid

from fastapi.testclient import TestClient
from remitx_api.app import create_app
from remitx_api.auth.dependencies import get_current_user
from remitx_api.config import TestConfig
from remitx_api.extensions import db
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.repositories.user_repository import UserRepository
from tests.rbac_helpers import (
    grant_role,
    make_user,
    rbac_client,
    revoke_role,
    seed_rbac_catalogue,
)

# Paths reachable with no credentials. Everything else the OpenAPI schema
# lists has to answer 401 to an anonymous caller. (/docs, /redoc and
# /openapi.json are FastAPI's own and never appear in the schema.)
PUBLIC_ALLOWLIST = frozenset({"/health"})

PERMISSION_VALUES = frozenset(code.value for code in PermissionCode)


def _every_operation(app) -> list[tuple[str, str]]:
    """(method, path) for every route the app publishes, path params filled in.

    Read off the OpenAPI schema rather than walked out of `app.routes`: a
    router included by reference keeps its gate in the include context, not on
    the route's own dependant, so inspecting dependency trees silently sees
    nothing and passes. Asking each route what it *answers* can't go quiet
    like that.
    """
    operations = []
    for path, methods in app.openapi()["paths"].items():
        concrete = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)
        for method in methods:
            operations.append((method.upper(), concrete))
    return operations


def test_every_route_answers_401_to_an_anonymous_caller(anonymous_client):
    for method, path in _every_operation(anonymous_client.app):
        response = anonymous_client.request(method, path)

        if path in PUBLIC_ALLOWLIST:
            assert response.status_code != 401, f"{method} {path} should be public"
        else:
            assert response.status_code == 401, f"{method} {path} has no auth gate"


def test_every_admin_route_is_gated_on_a_permission():
    """The guard PR #70 needed: a route under /admin that gates on anything
    other than a `PermissionCode` — "is this caller an admin", a role name, a
    flag on the User row — fails here, because only `RequirePermission`
    answers a permissionless caller with the permission it wanted.
    """
    with rbac_client(make_user("nobody")) as client:
        for method, path in _every_operation(client.app):
            response = client.request(method, path)

            if not path.startswith("/admin"):
                assert response.status_code != 403, (
                    f"{method} {path} is not an admin route but 403s"
                )
                continue

            assert response.status_code == 403, (
                f"{method} {path} missing admin permission gate"
            )
            detail = response.json()["detail"]
            assert detail.startswith("Missing permission: "), (
                f"{method} {path} is gated, but not on a permission: {detail}"
            )
            assert detail.removeprefix("Missing permission: ") in PERMISSION_VALUES


def test_require_permission_returns_401_when_unauthenticated(anonymous_client):
    response = anonymous_client.get("/admin/roles")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_require_permission_returns_403_without_permission():
    with rbac_client(make_user("a")) as client:
        response = client.get("/admin/roles")

    assert response.status_code == 403
    assert response.json()["detail"] == (
        f"Missing permission: {PermissionCode.ROLE_READ.value}"
    )


def test_me_permissions_empty_for_customer_with_no_roles():
    with rbac_client(make_user("a")) as client:
        response = client.get("/me/permissions")

    assert response.status_code == 200
    assert response.json() == {"permissions": [], "is_admin": False}


def test_me_roles_includes_descriptions():
    with rbac_client(make_user("a"), roles=("iam_admin",)) as client:
        response = client.get("/me/roles")

    assert response.status_code == 200
    roles = response.json()
    assert len(roles) == 1
    assert roles[0]["name"] == "iam_admin"
    assert roles[0]["description"]
    permissions = {item["permission"]: item for item in roles[0]["permissions"]}
    assert PermissionCode.ROLE_READ.value in permissions
    assert permissions[PermissionCode.ROLE_READ.value]["description"]


def test_me_permissions_lists_granted_role_permissions():
    with rbac_client(make_user("a"), roles=("support_agent",)) as client:
        response = client.get("/me/permissions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_admin"] is True
    permissions = payload["permissions"]
    assert PermissionCode.TRANSACTION_READ_ANY.value in permissions
    assert PermissionCode.ROLE_READ.value not in permissions


def test_admin_list_roles_returns_seeded_catalogue():
    with rbac_client(make_user("a"), roles=("iam_admin",)) as client:
        response = client.get("/admin/roles")

    assert response.status_code == 200
    roles = response.json()
    assert len(roles) == 9

    compliance_officer = next(
        role for role in roles if role["name"] == "compliance_officer"
    )
    assert compliance_officer["display_name"] == "Compliance Officer"
    assert (
        PermissionCode.KYC_APPLICATION_DECIDE.value in compliance_officer["permissions"]
    )

    customer = next(role for role in roles if role["name"] == "customer")
    assert customer["permissions"] == []


def test_revoked_role_takes_effect_on_next_request():
    user = make_user("a")
    app = create_app(TestConfig)
    app.dependency_overrides[get_current_user] = lambda: user

    with TestClient(app) as client:
        token = db.open_session()
        try:
            UserRepository().save(user)
            seed_rbac_catalogue()
            assignment = grant_role(user.id, "iam_admin")
            assert client.get("/admin/roles").status_code == 200
            revoke_role(assignment)
            assert client.get("/admin/roles").status_code == 403
        finally:
            db.close_session(token)


def test_admin_handlers_have_no_ad_hoc_permission_checks():
    """Access is decided before the handler runs, or it isn't decided at all:
    a handler that reaches for the caller's permissions is re-implementing the
    gate somewhere nothing audits.
    """
    from remitx_api.routes.admin import deposits, roles, user_roles, users

    handlers = (
        roles.list_roles,
        roles.list_toxic_combinations,
        users.update_kyc_status,
        user_roles.list_admins,
        user_roles.search_users,
        user_roles.get_user_access,
        user_roles.grant_user_role,
        user_roles.revoke_user_role,
        deposits.process_deposits,
        deposits.list_pending_deposits,
        deposits.approve_deposit,
    )

    for handler in handlers:
        names = handler.__code__.co_names
        assert "permission" not in names, handler.__name__
        assert "PermissionCode" not in names, handler.__name__
        assert "role" not in names, handler.__name__
