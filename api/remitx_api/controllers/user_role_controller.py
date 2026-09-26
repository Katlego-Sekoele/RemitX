"""Granting and revoking operational roles.

Grants are append-only: granting inserts a ``user_roles`` row, revoking
stamps ``revoked_at`` and a reason on the live one. Nothing is deleted, so
the table answers "who could do this in September, and who gave them that?"
long after the fact.

Enforcement is not here — routes gate on a ``PermissionCode`` before a
handler runs (auth/permissions.py). What *is* here is the orchestration
around rules the catalogue itself carries: ``roles.is_grantable``,
``roles.protect_last_holder``, and the ``toxic_combinations`` rows. None of
those are role names or permission pairs written into this module, so
changing a rule is an ``UPDATE``, not a redeploy.

Each use case commits once through ``@db_transaction`` rather than
calling ``db.session`` directly — see CLAUDE.md.
"""

import uuid

from remitx_api.clock import utcnow
from remitx_api.db.transaction import db_transaction
from remitx_api.errors.roles import (
    LastProtectedRoleHolderError,
    RoleNotGrantableError,
    RoleNotHeldError,
    UnknownRoleError,
)
from remitx_api.extensions import db
from remitx_api.models.orm.audit_log import AuditAction, AuditSubject
from remitx_api.models.orm.role import Role
from remitx_api.models.orm.user_role import UserRole
from remitx_api.models.schemas.role import (
    AdminMemberRead,
    AdminRoleRead,
    RoleGrantRequest,
    RoleGrantResult,
    ToxicCombinationRead,
    UserAccessRead,
    UserRoleRead,
)
from remitx_api.repositories.permission_repository import PermissionRepository
from remitx_api.repositories.role_repository import RoleRepository
from remitx_api.repositories.toxic_combination_repository import (
    ToxicCombinationRepository,
)
from remitx_api.repositories.user_repository import UserRepository
from remitx_api.repositories.user_role_repository import UserRoleRepository
from remitx_api.services.audit_service import record_audit


class UserRoleController:
    def __init__(self) -> None:
        self._users = UserRepository()
        self._roles = RoleRepository()
        self._assignments = UserRoleRepository()
        self._permissions = PermissionRepository()
        self._toxic_combinations = ToxicCombinationRepository()

    def get_access(self, user_id: uuid.UUID) -> UserAccessRead:
        """One person's grant history, plus what it currently adds up to."""
        user = self._users.require_by_id(user_id)
        history = self._assignments.list_history_for_user(user_id)

        return UserAccessRead(
            user_id=user.id,
            email=user.email,
            base_reference=user.base_reference,
            permissions=sorted(
                code.value
                for code in self._permissions.get_effective_permissions(user_id)
            ),
            roles=[
                _to_user_role_read(assignment, role) for assignment, role in history
            ],
        )

    @db_transaction
    def grant(
        self,
        user_id: uuid.UUID,
        request: RoleGrantRequest,
        actor_id: uuid.UUID,
    ) -> RoleGrantResult:
        """Give a user a role, recording who, why, and what it creates.

        Idempotent by design: a user who already holds the role gets their
        existing grant back rather than a second row. The partial unique
        index on ``user_roles`` says the same thing at the database level,
        but answering the caller beats making them read an IntegrityError.
        """
        user = self._users.require_by_id(user_id)
        role = self._require_role(request.role)
        if not role.is_grantable:
            raise RoleNotGrantableError(role.name)

        existing = self._assignments.get_active(user.id, role.role_id)
        if existing is not None:
            return RoleGrantResult(
                grant=_to_user_role_read(existing, role),
                created=False,
                toxic_combinations=self._warnings_for(user.id),
            )

        assignment = UserRole(
            user_id=user.id,
            role_id=role.role_id,
            granted_by=actor_id,
            granted_at=utcnow(),
            grant_reason=request.reason.strip(),
            self_granted=actor_id == user.id,
        )
        db.session.add(assignment)
        db.session.flush()

        # Computed after the insert so it describes the access the user now
        # actually has, not a projection the client asked us to trust. A
        # caller that skipped the warning is recorded as not having accepted
        # one, which is the signal worth keeping.
        warnings = self._warnings_for(user.id)
        assignment.toxic_combination_acknowledged = bool(warnings) and (
            request.toxic_combination_acknowledged
        )
        if actor_id is not None:
            record_audit(
                actor_user_id=actor_id,
                subject_type=AuditSubject.USER_ROLE,
                subject_id=assignment.user_role_id,
                action=AuditAction.ROLE_GRANTED,
                after={
                    "role": role.name,
                    "user_id": str(user.id),
                    "self_granted": assignment.self_granted,
                },
                reason=assignment.grant_reason,
            )
        return RoleGrantResult(
            grant=_to_user_role_read(assignment, role),
            created=True,
            toxic_combinations=warnings,
        )

    @db_transaction
    def revoke(
        self,
        user_id: uuid.UUID,
        role_name: str,
        reason: str,
        actor_id: uuid.UUID,
    ) -> UserRoleRead:
        """Take a role back, keeping the row and stamping why it ended.

        Takes effect on the holder's very next request: permissions resolve
        from ``user_roles`` per request (auth/permissions.py), so there is no
        session or token to wait out.
        """
        user = self._users.require_by_id(user_id)
        role = self._require_role(role_name)

        assignment = self._assignments.get_active(user.id, role.role_id)
        if assignment is None:
            raise RoleNotHeldError(role_name)

        if (
            role.protect_last_holder
            and self._assignments.count_active_holders(role.role_id) <= 1
        ):
            raise LastProtectedRoleHolderError(role.name)

        assignment.revoked_at = utcnow()
        assignment.revoked_by = actor_id
        assignment.revoke_reason = reason.strip()
        if actor_id is not None:
            record_audit(
                actor_user_id=actor_id,
                action=AuditAction.ROLE_REVOKED,
                subject_type=AuditSubject.USER_ROLE,
                subject_id=assignment.user_role_id,
                before={"role": role.name, "user_id": str(user.id)},
                reason=assignment.revoke_reason,
            )

        return _to_user_role_read(assignment, role)

    def list_admins(self) -> list[AdminMemberRead]:
        """Everyone holding at least one role, self-grants surfaced first.

        A self-grant is legitimate and visible rather than forbidden and
        worked around, so the list leads with the rows that deserve a second
        look — then falls back to most recently changed.
        """
        members: dict[uuid.UUID, dict] = {}
        for user, role, assignment in self._assignments.list_admins():
            entry = members.setdefault(
                user.id,
                {"user": user, "roles": []},
            )
            entry["roles"].append(
                AdminRoleRead(
                    role=role.name,
                    display_name=role.role_display_name,
                    granted_at=assignment.granted_at,
                    self_granted=assignment.self_granted,
                )
            )

        admins = [
            AdminMemberRead(
                user_id=entry["user"].id,
                email=entry["user"].email,
                base_reference=entry["user"].base_reference,
                roles=entry["roles"],
                last_granted_at=max(item.granted_at for item in entry["roles"]),
                has_self_grant=any(item.self_granted for item in entry["roles"]),
            )
            for entry in members.values()
        ]
        admins.sort(
            key=lambda member: (
                not member.has_self_grant,
                -member.last_granted_at.timestamp(),
            )
        )
        return admins

    def _warnings_for(self, user_id: uuid.UUID) -> list[ToxicCombinationRead]:
        held = {
            code.value for code in self._permissions.get_effective_permissions(user_id)
        }
        return [
            ToxicCombinationRead(permissions=[first, second], explanation=explanation)
            for first, second, explanation in self._toxic_combinations.list_pairs()
            if first in held and second in held
        ]

    def _require_role(self, role_name: str) -> Role:
        role = self._roles.get_by_name(role_name)
        if role is None:
            raise UnknownRoleError(role_name)
        return role


def _to_user_role_read(assignment: UserRole, role: Role) -> UserRoleRead:
    return UserRoleRead(
        user_role_id=assignment.user_role_id,
        role=role.name,
        display_name=role.role_display_name,
        granted_at=assignment.granted_at,
        granted_by=assignment.granted_by,
        grant_reason=assignment.grant_reason,
        self_granted=assignment.self_granted,
        toxic_combination_acknowledged=assignment.toxic_combination_acknowledged,
        revoked_at=assignment.revoked_at,
        revoked_by=assignment.revoked_by,
        revoke_reason=assignment.revoke_reason,
    )
