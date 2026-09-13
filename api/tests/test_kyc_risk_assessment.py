"""Risk rating, tiers and PEP rules end to end through `KycController`: what
submission stores, what an override keeps, who may decide, what a tier needs,
and what a customer may then send — all against the rule rows in the database.
"""

import uuid
from decimal import Decimal

import pytest
from remitx_api.controllers.kyc_controller import KycController
from remitx_api.errors.kyc import (
    IncompleteKycDeclarationError,
    KycRiskOverrideNotAllowedError,
    KycRiskRulesMisconfiguredError,
    KycSeniorApprovalRequiredError,
    KycTierNotGrantableError,
    KycVersionConflictError,
    UnknownKycRiskRatingError,
)
from remitx_api.extensions import db
from remitx_api.models.orm.kyc_application import KycApplication
from remitx_api.models.orm.kyc_application_risk_view import kyc_application_risk
from remitx_api.models.orm.kyc_assessment_audit import KycAssessmentAudit
from remitx_api.models.orm.kyc_lifecycle import KycReasonCode, KycStatus
from remitx_api.models.orm.kyc_risk_rating import KycRiskRatingRecord
from remitx_api.models.orm.kyc_risk_signal import KycRiskSignalRecord
from remitx_api.models.orm.kyc_tier import KycTier
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.repositories.kyc_application_repository import (
    KycApplicationRepository,
)
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from tests.kyc_helpers import insert_application, make_user, seed_kyc_reference_data
from tests.rbac_helpers import grant_permissions, grant_role, seed_rbac_catalogue

SOURCE_OF_WEALTH = "Salary as a senior civil servant, and an inherited house."
PEP = {
    "is_domestic_prominent_influential_person": True,
    "pep_relationship": "self",
    "pep_position": "Deputy Director-General",
    "pep_country": "ZA",
    "source_of_wealth": SOURCE_OF_WEALTH,
}


@pytest.fixture(autouse=True)
def _seed(app_context):
    seed_kyc_reference_data()
    seed_rbac_catalogue()


@pytest.fixture
def controller():
    return KycController()


@pytest.fixture
def officer():
    user = make_user()
    grant_role(user.id, "compliance_officer")
    return user


@pytest.fixture
def analyst():
    user = make_user()
    grant_role(user.id, "compliance_analyst")
    return user


def _draft(**declared) -> KycApplication:
    return insert_application(make_user().id, with_pii=True, **declared)


def _submit(controller, application: KycApplication) -> KycApplication:
    return controller.transition(
        application.application_id,
        KycStatus.SUBMITTED,
        expected_version=application.version,
    )


def _claim(controller, application: KycApplication, reviewer) -> KycApplication:
    return controller.transition(
        application.application_id,
        KycStatus.UNDER_REVIEW,
        expected_version=application.version,
        actor_user_id=reviewer.id,
    )


def _audit(application_id: uuid.UUID):
    return KycApplicationRepository().list_assessment_audit(application_id)


def _reload(application_id: uuid.UUID) -> KycApplication:
    db.session.expire_all()
    return db.session.get(KycApplication, application_id)


# --- submission scores the application ---------------------------------------------


def test_submission_stores_the_score_rating_and_the_signals_behind_them(controller):
    application = _draft(nationality="ZW", id_type="passport", issuing_country="ZW")

    submitted = _submit(controller, application)

    assert submitted.risk_score == 50
    assert submitted.risk_rating == "medium"
    assert submitted.risk_rating_override is None
    assert submitted.effective_risk_rating == "medium"

    ((entry, signals),) = _audit(application.application_id)
    assert entry.computed_risk_rating == entry.final_risk_rating == "medium"
    assert entry.risk_score == 50
    assert entry.reason is None
    assert entry.final_tier is None
    assert sorted((row.signal, row.score_effect) for row in signals) == [
        ("nationality_differs_from_residence", 25),
        ("non_national_identity_document", 25),
    ]


def test_a_clean_sa_applicant_is_low_with_no_signals(controller):
    submitted = _submit(controller, _draft())

    assert submitted.risk_score == 0
    assert submitted.risk_rating == "low"
    ((_entry, signals),) = _audit(submitted.application_id)
    assert signals == []


def test_a_pep_declaration_is_high(controller):
    assert _submit(controller, _draft(**PEP)).risk_rating == "high"


def test_a_pep_declaration_without_source_of_wealth_cannot_be_submitted(controller):
    application = _draft(**{**PEP, "source_of_wealth": None})

    with pytest.raises(IncompleteKycDeclarationError, match="source_of_wealth"):
        _submit(controller, application)

    reloaded = _reload(application.application_id)
    assert reloaded.status == KycStatus.IN_PROGRESS.value
    assert reloaded.version == 1
    assert reloaded.risk_score is None
    assert _audit(application.application_id) == []


def test_source_of_funds_other_needs_its_free_text_to_submit(controller):
    with pytest.raises(IncompleteKycDeclarationError, match="source_of_funds_detail"):
        _submit(controller, _draft(source_of_funds="other"))


def test_scoring_reads_the_weights_in_the_database(controller):
    """Reweighting a row changes the next submission — no release involved."""
    db.session.execute(
        update(KycRiskSignalRecord)
        .where(KycRiskSignalRecord.signal == "non_national_identity_document")
        .values(score_effect=70)
    )
    db.session.commit()

    submitted = _submit(controller, _draft(id_type="passport"))

    assert submitted.risk_score == 70
    assert submitted.risk_rating == "high"


def test_a_deactivated_signal_scores_nothing(controller):
    db.session.execute(
        update(KycRiskSignalRecord)
        .where(KycRiskSignalRecord.signal == "nationality_differs_from_residence")
        .values(is_active=False)
    )
    db.session.commit()

    submitted = _submit(controller, _draft(nationality="ZW"))

    assert submitted.risk_score == 0


def test_reweighting_later_does_not_rewrite_an_earlier_assessment(controller):
    """The stored score and the audited signal effects are what the application
    was assessed on — a later reweight is not retroactive."""
    earlier = _submit(controller, _draft(id_type="passport"))

    db.session.execute(
        update(KycRiskSignalRecord)
        .where(KycRiskSignalRecord.signal == "non_national_identity_document")
        .values(score_effect=70)
    )
    db.session.commit()

    reloaded = _reload(earlier.application_id)
    assert reloaded.risk_score == 25
    ((_entry, (signal,)),) = _audit(earlier.application_id)
    assert signal.score_effect == 25


def test_a_broken_band_table_fails_loudly_instead_of_mis_rating(controller):
    db.session.execute(
        update(KycRiskRatingRecord)
        .where(KycRiskRatingRecord.rating == "medium")
        .values(min_score=30)
    )
    db.session.commit()

    with pytest.raises(KycRiskRulesMisconfiguredError):
        _submit(controller, _draft())


# --- reviewer override ---------------------------------------------------------------


def test_an_override_is_stored_beside_the_computed_rating(controller, officer):
    submitted = _submit(controller, _draft())
    version_on_screen = submitted.version

    overridden = controller.override_risk_rating(
        submitted.application_id,
        "high",
        reason="  Declared employer is a shell company registered last month.  ",
        expected_version=version_on_screen,
        actor_user_id=officer.id,
    )

    assert overridden.risk_rating == "low"
    assert overridden.risk_score == 0
    assert overridden.risk_rating_override == "high"
    assert overridden.effective_risk_rating == "high"
    assert overridden.risk_rating_override_reason == (
        "Declared employer is a shell company registered last month."
    )
    assert overridden.risk_rating_overridden_by_user_id == officer.id
    assert overridden.version == version_on_screen + 1

    (_scored, (entry, _signals)) = _audit(submitted.application_id)
    assert entry.computed_risk_rating == "low"
    assert entry.final_risk_rating == "high"
    assert entry.reason.startswith("Declared employer")
    assert entry.actor_user_id == officer.id


def test_an_override_adds_no_status_history(controller, officer):
    submitted = _submit(controller, _draft())
    repo = KycApplicationRepository()
    before = repo.list_application_history(submitted.application_id)

    controller.override_risk_rating(
        submitted.application_id,
        "high",
        reason="Adverse information from the reviewer's own notes.",
        expected_version=submitted.version,
        actor_user_id=officer.id,
    )

    after = repo.list_application_history(submitted.application_id)
    assert [row.history_id for row in after] == [row.history_id for row in before]


def test_the_view_reports_the_effective_rating_and_its_consequences(
    controller, officer
):
    submitted = _submit(controller, _draft())
    controller.override_risk_rating(
        submitted.application_id,
        "high",
        reason="Adverse information from the reviewer's own notes.",
        expected_version=submitted.version,
        actor_user_id=officer.id,
    )

    row = db.session.execute(
        select(kyc_application_risk).where(
            kyc_application_risk.c.application_id == submitted.application_id
        )
    ).one()

    assert row.risk_score == 0
    assert row.computed_risk_rating == "low"
    assert row.effective_risk_rating == "high"
    assert row.max_tier == 1
    assert row.limit_percent == 50
    assert bool(row.requires_senior_approval) is True


def test_an_override_survives_resubmission(controller, officer):
    """Resubmitting after more_info_required rescores the application, but an
    applicant cannot shed a reviewer's `high` by editing a field."""
    application = _claim(controller, _submit(controller, _draft()), officer)
    application = controller.override_risk_rating(
        application.application_id,
        "high",
        reason="Source of funds documents look altered.",
        expected_version=application.version,
        actor_user_id=officer.id,
    )
    application = controller.transition(
        application.application_id,
        KycStatus.MORE_INFO_REQUIRED,
        expected_version=application.version,
        actor_user_id=officer.id,
        reason_code=KycReasonCode.DOCUMENT_ILLEGIBLE,
    )
    application = controller.transition(
        application.application_id,
        KycStatus.IN_PROGRESS,
        expected_version=application.version,
    )

    resubmitted = _submit(controller, application)

    assert resubmitted.risk_rating == "low"
    assert resubmitted.effective_risk_rating == "high"
    rescored, _signals = _audit(application.application_id)[-1]
    assert rescored.computed_risk_rating == "low"
    assert rescored.final_risk_rating == "high"
    assert rescored.reason == "Source of funds documents look altered."


def test_a_decided_application_cannot_have_its_rating_overridden(controller, officer):
    application = insert_application(make_user().id, KycStatus.APPROVED)

    with pytest.raises(KycRiskOverrideNotAllowedError):
        controller.override_risk_rating(
            application.application_id,
            "high",
            reason="Too late for this, it is already approved.",
            expected_version=application.version,
            actor_user_id=officer.id,
        )


def test_an_override_from_a_stale_page_loses(controller, officer):
    submitted = _submit(controller, _draft())

    with pytest.raises(KycVersionConflictError):
        controller.override_risk_rating(
            submitted.application_id,
            "high",
            reason="Looking at an old copy of the application.",
            expected_version=submitted.version - 1,
            actor_user_id=officer.id,
        )


def test_an_override_to_a_rating_that_is_not_a_row_is_refused(controller, officer):
    submitted = _submit(controller, _draft())

    with pytest.raises(UnknownKycRiskRatingError):
        controller.override_risk_rating(
            submitted.application_id,
            "extreme",
            reason="There is no such rating in the catalogue.",
            expected_version=submitted.version,
            actor_user_id=officer.id,
        )


# --- who may decide ------------------------------------------------------------------


@pytest.mark.parametrize("outcome", [KycStatus.APPROVED, KycStatus.REJECTED])
def test_an_analyst_cannot_decide_a_pep_application(
    controller, analyst, officer, outcome
):
    application = _claim(controller, _submit(controller, _draft(**PEP)), officer)

    with pytest.raises(KycSeniorApprovalRequiredError):
        controller.transition(
            application.application_id,
            outcome,
            expected_version=application.version,
            actor_user_id=analyst.id,
            reason_code=KycReasonCode.IDENTITY_VERIFIED,
        )

    assert _reload(application.application_id).status == (KycStatus.UNDER_REVIEW.value)


def test_an_officer_can_decide_a_pep_application(controller, officer):
    application = _claim(controller, _submit(controller, _draft(**PEP)), officer)

    approved = controller.transition(
        application.application_id,
        KycStatus.APPROVED,
        expected_version=application.version,
        actor_user_id=officer.id,
    )

    assert approved.status == KycStatus.APPROVED.value
    assert approved.tier_granted == 1


def test_a_pep_still_needs_an_officer_when_the_pep_signal_is_switched_off(
    controller, analyst, officer
):
    """The PEP rule is FICA's senior-approval requirement, not a score
    threshold — reweighting cannot route a PEP to an analyst."""
    db.session.execute(
        update(KycRiskSignalRecord)
        .where(KycRiskSignalRecord.signal == "pep_declared")
        .values(is_active=False)
    )
    db.session.commit()
    application = _claim(controller, _submit(controller, _draft(**PEP)), officer)
    assert application.risk_rating == "low"

    with pytest.raises(KycSeniorApprovalRequiredError):
        controller.transition(
            application.application_id,
            KycStatus.APPROVED,
            expected_version=application.version,
            actor_user_id=analyst.id,
        )


def test_a_senior_approval_rating_needs_an_officer_without_a_pep(
    controller, analyst, officer
):
    application = _claim(controller, _submit(controller, _draft()), officer)
    application = controller.override_risk_rating(
        application.application_id,
        "high",
        reason="Adverse media found by the reviewer.",
        expected_version=application.version,
        actor_user_id=officer.id,
    )

    with pytest.raises(KycSeniorApprovalRequiredError):
        controller.transition(
            application.application_id,
            KycStatus.APPROVED,
            expected_version=application.version,
            actor_user_id=analyst.id,
        )


def test_an_analyst_can_still_ask_a_pep_for_more_information(
    controller, analyst, officer
):
    application = _claim(controller, _submit(controller, _draft(**PEP)), officer)

    sent_back = controller.transition(
        application.application_id,
        KycStatus.MORE_INFO_REQUIRED,
        expected_version=application.version,
        actor_user_id=analyst.id,
        reason_code=KycReasonCode.DOCUMENT_MISSING,
    )

    assert sent_back.status == KycStatus.MORE_INFO_REQUIRED.value


# --- tiers -------------------------------------------------------------------------


def _approve(controller, application, actor, **kwargs):
    return controller.transition(
        application.application_id,
        KycStatus.APPROVED,
        expected_version=application.version,
        actor_user_id=actor.id,
        **kwargs,
    )


def test_approval_grants_tier_1_by_default_and_audits_it(controller, officer):
    application = _claim(controller, _submit(controller, _draft()), officer)

    approved = _approve(controller, application, officer)

    assert approved.tier_granted == 1
    entry, _signals = _audit(application.application_id)[-1]
    assert (entry.computed_tier, entry.final_tier, entry.reason) == (1, 1, None)
    assert entry.final_risk_rating is None


def test_an_officer_can_grant_tier_2_with_source_of_wealth_and_a_reason(
    controller, officer
):
    application = _claim(
        controller,
        _submit(controller, _draft(source_of_wealth=SOURCE_OF_WEALTH)),
        officer,
    )

    approved = _approve(
        controller,
        application,
        officer,
        tier_granted=2,
        reason_text="Payslips and property deeds support the declared wealth.",
    )

    assert approved.tier_granted == 2
    entry, _signals = _audit(application.application_id)[-1]
    assert (entry.computed_tier, entry.final_tier) == (1, 2)
    assert entry.reason.startswith("Payslips")


def test_tier_2_needs_a_source_of_wealth(controller, officer):
    application = _claim(controller, _submit(controller, _draft()), officer)

    with pytest.raises(KycTierNotGrantableError, match="source of wealth"):
        _approve(
            controller,
            application,
            officer,
            tier_granted=2,
            reason_text="Wants a higher limit.",
        )


def test_tier_2_needs_a_reason(controller, officer):
    application = _claim(
        controller,
        _submit(controller, _draft(source_of_wealth=SOURCE_OF_WEALTH)),
        officer,
    )

    with pytest.raises(KycTierNotGrantableError, match="reason"):
        _approve(controller, application, officer, tier_granted=2)


def test_tier_2_needs_the_risk_write_permission(controller, officer):
    decider = make_user()
    grant_permissions(decider.id, PermissionCode.KYC_APPLICATION_DECIDE)
    application = _claim(
        controller,
        _submit(controller, _draft(source_of_wealth=SOURCE_OF_WEALTH)),
        officer,
    )

    with pytest.raises(KycSeniorApprovalRequiredError, match="kyc:risk:write"):
        _approve(
            controller,
            application,
            decider,
            tier_granted=2,
            reason_text="Deciders without kyc:risk:write cannot do this.",
        )


def test_a_high_rating_caps_the_tier(controller, officer):
    application = _claim(controller, _submit(controller, _draft(**PEP)), officer)

    with pytest.raises(KycTierNotGrantableError, match="tier 1 at most"):
        _approve(
            controller,
            application,
            officer,
            tier_granted=2,
            reason_text="PEP with documented wealth, still capped.",
        )


@pytest.mark.parametrize("tier", [0, 9])
def test_approval_cannot_grant_tier_0_or_an_undefined_tier(controller, officer, tier):
    application = _claim(controller, _submit(controller, _draft()), officer)

    with pytest.raises(KycTierNotGrantableError):
        _approve(
            controller,
            application,
            officer,
            tier_granted=tier,
            reason_text="Not a tier an approval can grant.",
        )


@pytest.mark.parametrize(("declared", "days"), [({}, 730), (PEP, 180)])
def test_the_next_review_follows_the_rating(controller, officer, declared, days):
    application = _claim(controller, _submit(controller, _draft(**declared)), officer)

    approved = _approve(controller, application, officer)

    assert (approved.next_review_at - approved.updated_at).days == days


# --- what the customer may send ----------------------------------------------------


@pytest.mark.parametrize(
    ("declared", "rating", "daily", "monthly"),
    [
        ({}, "low", "3000.00", "25000.00"),
        ({"nationality": "ZW"}, "medium", "2250.00", "18750.00"),
        (PEP, "high", "1500.00", "12500.00"),
    ],
)
def test_standing_limits_are_the_tier_scaled_by_risk(
    controller, officer, declared, rating, daily, monthly
):
    application = _claim(controller, _submit(controller, _draft(**declared)), officer)
    _approve(controller, application, officer)

    standing = controller.get_standing(application.user_id)

    assert standing.risk_rating == rating
    assert standing.daily_limit_zar == Decimal(daily)
    assert standing.monthly_limit_zar == Decimal(monthly)


def test_a_changed_tier_limit_applies_to_existing_customers(controller, officer):
    application = _claim(controller, _submit(controller, _draft()), officer)
    _approve(controller, application, officer)

    db.session.execute(
        update(KycTier).where(KycTier.tier == 1).values(daily_limit_zar=4000)
    )
    db.session.commit()

    assert controller.get_standing(application.user_id).daily_limit_zar == Decimal(
        "4000.00"
    )


def test_an_unverified_user_can_send_nothing(controller):
    standing = controller.get_standing(make_user().id)

    assert standing.daily_limit_zar == Decimal("0")
    assert standing.monthly_limit_zar == Decimal("0")


# --- what the database refuses on its own -----------------------------------------


def test_the_database_refuses_an_unexplained_difference_in_the_audit(controller):
    application = _submit(controller, _draft())

    db.session.add(
        KycAssessmentAudit(
            application_id=application.application_id,
            computed_risk_rating="low",
            final_risk_rating="high",
        )
    )
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_the_database_refuses_an_override_without_a_reason(controller):
    application = _submit(controller, _draft())

    with pytest.raises(IntegrityError):
        db.session.execute(
            update(KycApplication)
            .where(KycApplication.application_id == application.application_id)
            .values(risk_rating_override="high")
        )
        db.session.commit()
    db.session.rollback()
