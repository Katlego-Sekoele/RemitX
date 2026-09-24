"""Verification, the way applicants and reviewers actually do it.

The applicant walks the wizard through `KycOnboardingController` (start, one
PATCH per step, the two documents through `KycDocumentController.store_document`,
then submit). Reviewers work the queue through `KycController`: an analyst
claims the application and may send it back for more information; an officer
decides, sometimes overriding the computed risk rating first. Risk scoring,
history rows, decisions, the audit log and every validation happen inside the
backend, exactly as they would for a real applicant.

Each person's path is decided before they start (`plan_path`), so their
documents can fit it: someone a reviewer will send back uploads a blurry ID.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from remitx_seeder.context import RunContext, SeededPerson
from remitx_seeder.data import load
from remitx_seeder.generators import documents
from remitx_seeder.sim import Simulation
from remitx_seeder.stories.timing import business_time

PATH_NEVER = "never_start"
PATH_ABANDON = "abandon"
PATH_APPROVE = "approve"
PATH_REJECT = "reject"
PATH_MORE_INFO = "more_info"
PATH_MORE_INFO_NO_REPLY = "more_info_no_reply"

OnVerified = Callable[[SeededPerson], None]


def plan_path(ctx: RunContext, person: SeededPerson) -> str:
    kyc = ctx.scenario.kyc
    roll = ctx.rng.random()
    if roll < kyc.never_start_rate:
        return PATH_NEVER
    roll = ctx.rng.random()
    if roll < kyc.abandon_rate:
        return PATH_ABANDON
    roll = ctx.rng.random()
    if roll < kyc.reject_rate:
        return PATH_REJECT
    if ctx.rng.random() < kyc.more_info_rate:
        if ctx.rng.random() < kyc.more_info_no_reply_rate:
            return PATH_MORE_INFO_NO_REPLY
        return PATH_MORE_INFO
    return PATH_APPROVE


class KycStory:
    def __init__(self, ctx: RunContext, sim: Simulation, on_verified: OnVerified):
        self.ctx = ctx
        self.sim = sim
        self.on_verified = on_verified

    # --- applicant ---------------------------------------------------------

    def schedule(self, person: SeededPerson, at: datetime) -> None:
        if person.kyc_path == PATH_NEVER:
            self.ctx.count("kyc.never_started")
            return
        self.sim.schedule(at, "kyc.start", lambda: self._start(person))

    def _start(self, person: SeededPerson) -> None:
        from remitx_api.controllers.kyc_onboarding_controller import (
            KycOnboardingController,
        )

        view = KycOnboardingController().start(
            person.user_id, residential_country=person.persona.residence
        )
        person.application_id = view.application.application_id
        self.ctx.count("kyc.applications")
        steps = self._steps(person)
        stop_after = len(steps)
        if person.kyc_path == PATH_ABANDON:
            stop_after = self.ctx.rng.randint(1, len(steps) - 1)
        self._run_steps(person, steps[:stop_after], submit=stop_after == len(steps))

    def _steps(self, person: SeededPerson) -> list[tuple[str, dict, list[str]]]:
        persona = person.persona
        ident = persona.identification
        address = persona.address
        blurry_id = person.kyc_path in (PATH_MORE_INFO, PATH_MORE_INFO_NO_REPLY)
        id_fields = {
            "id_type": ident.id_type,
            "issuing_country": ident.issuing_country,
            "id_number": ident.number,
        }
        if ident.expiry is not None:
            id_fields["id_expiry_date"] = ident.expiry.isoformat()
        financial = {
            "source_of_funds": persona.source_of_funds,
            "expected_monthly_volume_zar": str(
                persona.expected_monthly_volume_zar or 0
            ),
        }
        if persona.source_of_funds_detail:
            financial["source_of_funds_detail"] = persona.source_of_funds_detail
        if persona.source_of_wealth:
            financial["source_of_wealth"] = persona.source_of_wealth
        pep = persona.pep
        declarations = {
            "is_domestic_prominent_influential_person": bool(pep and pep["domestic"]),
            "is_foreign_prominent_public_official": bool(pep and pep["foreign"]),
            "is_pep_family_or_close_associate": bool(
                pep and pep["family_or_associate"]
            ),
        }
        if pep:
            declarations.update(
                pep_relationship=pep["relationship"],
                pep_position=pep["position"],
                pep_country=pep["country"],
                pep_details=pep["details"],
            )
        return [
            (
                "identity",
                {
                    "full_name": persona.full_name,
                    "date_of_birth": persona.date_of_birth.isoformat(),
                    "nationality": persona.nationality,
                },
                [],
            ),
            (
                "id-document",
                id_fields,
                ["id_document_blurry" if blurry_id else "id_document"],
            ),
            (
                "address",
                {
                    "residential_line1": address.line1,
                    "residential_line2": address.line2,
                    "residential_city": address.city,
                    "residential_postal_code": address.postal_code,
                    "residential_country": address.country,
                },
                ["proof_of_address"],
            ),
            ("contact", {"mobile_number": persona.mobile, "email": person.email}, []),
            ("financial", financial, []),
            ("declarations", declarations, []),
        ]

    def _run_steps(self, person: SeededPerson, steps: list, *, submit: bool) -> None:
        """One step now, the rest as follow-up events a few minutes (or, now
        and then, a day or two) apart: people save and come back."""
        if not steps:
            if submit:
                self._submit(person)
            else:
                self.ctx.count("kyc.abandoned")
            return
        name, fields, uploads = steps[0]
        self._patch(person, fields)
        for kind in uploads:
            self._upload(person, kind)
        gap = timedelta(minutes=self.ctx.rng.uniform(1, 9))
        if self.ctx.rng.random() < 0.1:
            gap = timedelta(days=self.ctx.rng.uniform(0.5, 3))
        self.sim.schedule(
            self.ctx.clock.now() + gap,
            f"kyc.step.{steps[1][0]}" if len(steps) > 1 else "kyc.submit",
            lambda: self._run_steps(person, steps[1:], submit=submit),
        )

    def _patch(self, person: SeededPerson, fields: dict) -> None:
        from remitx_api.controllers.kyc_onboarding_controller import (
            KycOnboardingController,
        )

        KycOnboardingController().patch(
            person.user_id,
            person.application_id,
            fields,
            expected_version=self._version(person),
        )

    def _upload(self, person: SeededPerson, kind: str) -> None:
        from remitx_api.controllers.kyc_document_controller import (
            KycDocumentController,
        )
        from remitx_api.models.orm.kyc_lifecycle import KycDocumentType

        if kind.startswith("id_document"):
            rendered = documents.identity_document(
                self.ctx.rng, person.persona, blurry=kind.endswith("_blurry")
            )
            document_type = KycDocumentType.ID_DOCUMENT
        else:
            statement_day = self.ctx.clock.now().date() - timedelta(
                days=self.ctx.rng.randint(3, 50)
            )
            rendered = documents.proof_of_address(
                self.ctx.rng, person.persona, statement_day
            )
            document_type = KycDocumentType.PROOF_OF_ADDRESS
        KycDocumentController().store_document(
            user_id=person.user_id,
            application_id=person.application_id,
            document_type=document_type,
            declared_content_type=rendered.content_type,
            body=rendered.body,
        )
        self.ctx.count("kyc.documents")
        if rendered.blurry:
            self.ctx.count("kyc.documents_blurry")

    def _submit(self, person: SeededPerson) -> None:
        from remitx_api.controllers.kyc_onboarding_controller import (
            KycOnboardingController,
        )

        KycOnboardingController().submit(
            person.user_id,
            person.application_id,
            expected_version=self._version(person),
            consent=True,
        )
        self.ctx.count("kyc.submitted")
        low, high = self.ctx.scenario.kyc.review_delay_hours
        claim_at = business_time(
            self.ctx.rng,
            self.ctx.clock.now() + timedelta(hours=self.ctx.rng.uniform(low, high)),
        )
        self.sim.schedule(claim_at, "kyc.review.claim", lambda: self._claim(person))

    # --- reviewers ---------------------------------------------------------

    def _claim(self, person: SeededPerson) -> None:
        from remitx_api.controllers.kyc_controller import KycController

        analysts = self.ctx.staff_by_role.get("compliance_analyst") or []
        reviewer = (
            self.ctx.rng.choice(analysts)
            if analysts
            else self.ctx.staff("compliance_officer")
        )
        KycController().start_review(
            person.application_id,
            expected_version=self._version(person),
            actor_user_id=reviewer.user_id,
        )
        decide_at = business_time(
            self.ctx.rng,
            self.ctx.clock.now() + timedelta(minutes=self.ctx.rng.uniform(8, 120)),
        )
        self.sim.schedule(decide_at, "kyc.review.decide", lambda: self._decide(person))

    def _decide(self, person: SeededPerson) -> None:
        path = person.kyc_path
        if path in (PATH_MORE_INFO, PATH_MORE_INFO_NO_REPLY):
            self._request_more_info(person)
        elif path == PATH_REJECT:
            self._reject(person)
        else:
            self._approve(person)

    def _request_more_info(self, person: SeededPerson) -> None:
        from remitx_api.controllers.kyc_controller import KycController
        from remitx_api.models.orm.kyc_lifecycle import KycStatus

        reasons = load("templates")["more_info_reasons"]["document_illegible"]
        analysts = self.ctx.staff_by_role.get("compliance_analyst") or []
        reviewer = (
            self.ctx.rng.choice(analysts)
            if analysts
            else self.ctx.staff("compliance_officer")
        )
        KycController().transition(
            person.application_id,
            KycStatus.MORE_INFO_REQUIRED,
            expected_version=self._version(person),
            actor_user_id=reviewer.user_id,
            reason_code="document_illegible",
            reason_text=self.ctx.rng.choice(reasons),
        )
        self.ctx.count("kyc.more_info_requested")
        if person.kyc_path == PATH_MORE_INFO_NO_REPLY:
            self.ctx.count("kyc.more_info_unanswered")
            return
        # They come back with a readable scan and submit again; the second
        # review goes the ordinary way.
        person.kyc_path = PATH_APPROVE
        reply_at = self.ctx.clock.now() + timedelta(days=self.ctx.rng.uniform(0.3, 5))

        def reply() -> None:
            self._upload(person, "id_document")
            self._submit(person)

        self.sim.schedule(reply_at, "kyc.more_info.reply", reply)

    def _reject(self, person: SeededPerson) -> None:
        from remitx_api.controllers.kyc_controller import KycController
        from remitx_api.models.orm.kyc_lifecycle import KycStatus

        templates = load("templates")["reject_reasons"]
        code = self.ctx.rng.choices(
            ["details_mismatch", "suspected_fraud", "other"], weights=[75, 10, 15]
        )[0]
        KycController().transition(
            person.application_id,
            KycStatus.REJECTED,
            expected_version=self._version(person),
            actor_user_id=self.ctx.staff("compliance_officer").user_id,
            reason_code=code,
            reason_text=self.ctx.rng.choice(templates[code]),
        )
        self.ctx.count("kyc.rejected")
        if (
            code != "suspected_fraud"
            and self.ctx.rng.random() < self.ctx.scenario.kyc.reapply_rate
        ):
            person.kyc_path = PATH_APPROVE
            self.schedule(
                person,
                self.ctx.clock.now() + timedelta(days=self.ctx.rng.uniform(2, 14)),
            )

    def _approve(self, person: SeededPerson) -> None:
        from remitx_api.controllers.kyc_controller import KycController
        from remitx_api.models.orm.kyc_lifecycle import KycStatus
        from remitx_api.repositories.kyc_application_repository import (
            KycApplicationRepository,
        )

        officer = self.ctx.staff("compliance_officer")
        controller = KycController()
        templates = load("templates")
        application = KycApplicationRepository().get_by_id(person.application_id)
        if (
            person.force_override
            or self.ctx.rng.random() < self.ctx.scenario.kyc.override_rate
        ):
            computed = application.effective_risk_rating or "medium"
            rating = self.ctx.rng.choice(
                [r for r in ("low", "medium", "high") if r != computed]
            )
            controller.override_risk_rating(
                person.application_id,
                rating,
                reason=self.ctx.rng.choice(templates["override_reasons"][rating]),
                expected_version=self._version(person),
                actor_user_id=officer.user_id,
            )
            self.ctx.count("kyc.rating_overridden")
            application = KycApplicationRepository().get_by_id(person.application_id)

        tier = None
        reason = self.ctx.rng.choice(templates["approve_notes"])
        if (
            person.persona.source_of_wealth
            and application.effective_risk_rating in ("low", "medium")
            and (
                person.force_tier_two
                or self.ctx.rng.random() < self.ctx.scenario.kyc.tier_two_rate
            )
        ):
            tier = 2
            reason = self.ctx.rng.choice(templates["tier_two_reasons"])
        controller.transition(
            person.application_id,
            KycStatus.APPROVED,
            expected_version=self._version(person),
            actor_user_id=officer.user_id,
            reason_code="identity_verified",
            reason_text=reason,
            tier_granted=tier,
        )
        person.verified = True
        self.ctx.count("kyc.approved")
        if tier == 2:
            self.ctx.count("kyc.approved_tier_2")
        self.on_verified(person)

    def _version(self, person: SeededPerson) -> int:
        from remitx_api.repositories.kyc_application_repository import (
            KycApplicationRepository,
        )

        return KycApplicationRepository().get_by_id(person.application_id).version
