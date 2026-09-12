import uuid
from contextlib import contextmanager

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from remitx_api.app import create_app
from remitx_api.auth.dependencies import get_current_user
from remitx_api.auth.permissions import RequirePermission
from remitx_api.config import TestConfig
from remitx_api.extensions import db
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.user import User
from remitx_api.repositories.user_repository import UserRepository
from tests.rbac_helpers import grant_role, revoke_role, seed_rbac_catalogue

PUBLIC_ALLOWLIST = frozenset(
    {
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
    }
)


def _collect_dependency_callables(route: APIRoute) -> list[object]:
    callables: list[object] = []

    def walk(dep) -> None:
        if dep.call is not None:
            callables.append(dep.call)
        for sub in dep.dependencies:
            walk(sub)

    walk(route.dependant)
    return callables


def _make_user(suffix: str) -> User:
    return User(
        id=uuid.uuid4(),
        clerk_user_id=f"user_{suffix}",
        email=f"{suffix}@example.com",
        base_reference=f"{suffix}1",
    )


@contextmanager
def rbac_client(user: User, *, roles: tuple[str, ...] = ()):
    """One app + database: seed catalogue, persist user, grant roles, then serve."""
    app = create_app(TestConfig)
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as client:
        token = db.open_session()
        try:
            UserRepository().save(user)
            seed_rbac_catalogue()
            for role_name in roles:
                grant_role(user.id, role_name)
            yield client
        finally:
            db.close_session(token)


def test_every_route_is_in_exactly_one_gate_family():
    app = create_app(TestConfig)

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.methods or route.methods <= {"HEAD", "OPTIONS"}:
            continue

        path = route.path
        deps = _collect_dependency_callables(route)

        if path in PUBLIC_ALLOWLIST:
            assert get_current_user not in deps, (
                f"{path} is public but carries get_current_user"
            )
            continue

        assert get_current_user in deps, f"{path} has no customer auth gate"

        admin_permissions = [dep for dep in deps if isinstance(dep, RequirePermission)]
        if path.startswith("/admin"):
            assert admin_permissions, f"{path} missing admin permission gate"
        else:
            assert not admin_permissions, (
                f"{path} carries admin permission outside /admin"
            )


def test_require_permission_returns_401_when_unauthenticated(anonymous_client):
    response = anonymous_client.get("/admin/roles")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_require_permission_returns_403_without_permission():
    with rbac_client(_make_user("a")) as client:
        response = client.get("/admin/roles")

    assert response.status_code == 403
    assert response.json()["detail"] == (
        f"Missing permission: {PermissionCode.ROLE_READ.value}"
    )


def test_me_permissions_empty_for_customer_with_no_roles():
    with rbac_client(_make_user("a")) as client:
        response = client.get("/me/permissions")

    assert response.status_code == 200
    assert response.json() == {"permissions": [], "is_admin": False}


def test_me_roles_includes_descriptions():
    with rbac_client(_make_user("a"), roles=("iam_admin",)) as client:
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
    with rbac_client(_make_user("a"), roles=("support_agent",)) as client:
        response = client.get("/me/permissions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_admin"] is True
    permissions = payload["permissions"]
    assert PermissionCode.TRANSACTION_READ_ANY.value in permissions
    assert PermissionCode.ROLE_READ.value not in permissions


def test_admin_list_roles_returns_seeded_catalogue():
    with rbac_client(_make_user("a"), roles=("iam_admin",)) as client:
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
    user = _make_user("a")
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


def test_admin_handler_has_no_ad_hoc_permission_check():
    from remitx_api.routes.admin import roles as admin_roles

    source = admin_roles.list_roles.__code__.co_names
    assert "permission" not in source
    assert "PermissionCode" not in source
