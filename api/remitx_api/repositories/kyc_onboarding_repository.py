"""Read the onboarding catalogue. The wizard's order and completeness live here."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from remitx_api.extensions import db
from remitx_api.models.orm.kyc_onboarding_editable_status import (
    KycOnboardingEditableStatus,
)
from remitx_api.models.orm.kyc_onboarding_requirement import (
    KycOnboardingRequirement,
)
from remitx_api.models.orm.kyc_onboarding_step import KycOnboardingStep


@dataclass(frozen=True, slots=True)
class OnboardingRequirement:
    step: str
    name: str
    kind: str
    required_when: str
    copy_on_resubmit: bool


@dataclass(frozen=True, slots=True)
class OnboardingStep:
    step: str
    position: int
    role: str
    description: str


@dataclass(frozen=True, slots=True)
class OnboardingCatalogue:
    steps: tuple[OnboardingStep, ...]
    requirements: tuple[OnboardingRequirement, ...]
    editable_statuses: frozenset[str]

    @property
    def entry_step(self) -> str:
        for step in self.steps:
            if step.role == "entry":
                return step.step
        raise RuntimeError("kyc_onboarding_steps has no entry step")

    @property
    def outcome_step(self) -> str:
        for step in self.steps:
            if step.role == "outcome":
                return step.step
        raise RuntimeError("kyc_onboarding_steps has no outcome step")

    @property
    def copy_fields(self) -> tuple[str, ...]:
        return tuple(
            requirement.name
            for requirement in self.requirements
            if requirement.kind == "field" and requirement.copy_on_resubmit
        )

    def requirements_for(self, step: str) -> tuple[OnboardingRequirement, ...]:
        return tuple(
            requirement for requirement in self.requirements if requirement.step == step
        )


class KycOnboardingRepository:
    def load(self) -> OnboardingCatalogue:
        steps = tuple(
            OnboardingStep(
                step=row.step,
                position=row.position,
                role=row.role,
                description=row.description,
            )
            for row in db.session.scalars(
                select(KycOnboardingStep).order_by(KycOnboardingStep.position)
            ).all()
        )
        if not steps:
            raise RuntimeError(
                "kyc_onboarding_steps is empty; seed the onboarding catalogue"
            )
        requirements = tuple(
            OnboardingRequirement(
                step=row.step,
                name=row.name,
                kind=row.kind,
                required_when=row.required_when,
                copy_on_resubmit=row.copy_on_resubmit,
            )
            for row in db.session.scalars(
                select(KycOnboardingRequirement).order_by(
                    KycOnboardingRequirement.step,
                    KycOnboardingRequirement.name,
                )
            ).all()
        )
        editable = frozenset(
            db.session.scalars(select(KycOnboardingEditableStatus.status)).all()
        )
        return OnboardingCatalogue(
            steps=steps,
            requirements=requirements,
            editable_statuses=editable,
        )
