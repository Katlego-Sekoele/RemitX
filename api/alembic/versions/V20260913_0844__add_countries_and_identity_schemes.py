"""add countries and identity schemes

Countries become a table — every ISO 3166-1 code, with `operates_in` true for
South Africa and the United States — and identification becomes a scheme per
country, so validation follows the issuing country instead of assuming a South
African ID. Along with it:

- the four country columns on `kyc_applications` reference `countries`. On
  Postgres the constraints are NOT VALID: every write from here on is checked,
  but applications declared before this revision are history (FICA §23) and
  are not rewritten to satisfy them;
- `id_expiry_date`, required by the catalogue when the scheme needs it;
- the two ZA-anchored risk signals are deactivated and replaced, never
  redefined, so assessments that fired them keep their meaning.

Not safe against the app version already running: it loads active signals from
the table and refuses a rule set with a signal it has no detector for, so
scoring fails until the API that ships with this revision is deployed.

Revision ID: bfcc9109c5c2
Revises: a8d3c1e90b24
Create Date: 2026-09-13 08:44:21.776725+00:00

"""

import sqlalchemy as sa
from alembic import op
from remitx_api.models.orm.country_seed import COUNTRY_SEEDS
from remitx_api.models.orm.kyc_seed import (
    ID_EXPIRY_REQUIREMENT_SEEDS,
    IDENTITY_SCHEME_SEEDS,
    JURISDICTION_RISK_SIGNAL_SEEDS,
    RETIRED_RISK_SIGNALS,
)

revision: str = "bfcc9109c5c2"
down_revision: str | None = "a8d3c1e90b24"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_COUNTRY_COLUMNS = (
    "nationality",
    "issuing_country",
    "residential_country",
    "pep_country",
)

_ID_DOCUMENT_STEP_BEFORE = "ID type, number, issuing country and the ID document."
_ID_DOCUMENT_STEP_AFTER = (
    "Issuing country, ID type, number, expiry where it applies, and the ID document."
)

_REQUIRED_WHEN_BEFORE = (
    "required_when IN ('always', 'declares_pep', 'source_of_funds_other', 'never')"
)
_REQUIRED_WHEN_AFTER = (
    "required_when IN ('always', 'declares_pep', 'source_of_funds_other', "
    "'id_requires_expiry', 'never')"
)

_steps = sa.table(
    "kyc_onboarding_steps",
    sa.column("step", sa.Text()),
    sa.column("description", sa.Text()),
)
_requirements = sa.table(
    "kyc_onboarding_requirements",
    sa.column("step", sa.Text()),
    sa.column("name", sa.Text()),
    sa.column("kind", sa.Text()),
    sa.column("required_when", sa.Text()),
    sa.column("copy_on_resubmit", sa.Boolean()),
)
_signals = sa.table(
    "kyc_risk_signals",
    sa.column("signal", sa.Text()),
    sa.column("description", sa.Text()),
    sa.column("score_effect", sa.SmallInteger()),
    sa.column("is_active", sa.Boolean()),
)


def upgrade() -> None:
    op.create_table(
        "countries",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("operates_in", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "length(code) = 2 AND code = upper(code)",
            name="countries_code_iso_alpha2",
        ),
        sa.PrimaryKeyConstraint("code"),
    )
    op.bulk_insert(
        sa.table(
            "countries",
            sa.column("code", sa.Text()),
            sa.column("name", sa.Text()),
            sa.column("operates_in", sa.Boolean()),
        ),
        [
            {"code": seed.code, "name": seed.name, "operates_in": seed.operates_in}
            for seed in COUNTRY_SEEDS
        ],
    )

    op.create_table(
        "kyc_identity_schemes",
        sa.Column("scheme", sa.Text(), nullable=False),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column("id_type", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("validator", sa.Text(), nullable=False),
        sa.Column("requires_expiry", sa.Boolean(), nullable=False),
        sa.Column("input_mode", sa.Text(), nullable=False),
        sa.Column("number_hint", sa.Text(), nullable=False),
        sa.Column("document_hint", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "id_type IN ('national_id', 'passport')",
            name="kyc_identity_schemes_id_type_valid",
        ),
        sa.CheckConstraint(
            "input_mode IN ('numeric', 'text')",
            name="kyc_identity_schemes_input_mode_valid",
        ),
        sa.ForeignKeyConstraint(["country"], ["countries.code"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("scheme"),
        sa.UniqueConstraint(
            "country",
            "id_type",
            name="uq_kyc_identity_schemes_country_id_type",
        ),
    )
    op.create_index(
        "uq_kyc_identity_schemes_one_fallback_per_type",
        "kyc_identity_schemes",
        ["id_type"],
        unique=True,
        postgresql_where=sa.text("country IS NULL"),
        sqlite_where=sa.text("country IS NULL"),
    )
    op.bulk_insert(
        sa.table(
            "kyc_identity_schemes",
            sa.column("scheme", sa.Text()),
            sa.column("country", sa.Text()),
            sa.column("id_type", sa.Text()),
            sa.column("label", sa.Text()),
            sa.column("validator", sa.Text()),
            sa.column("requires_expiry", sa.Boolean()),
            sa.column("input_mode", sa.Text()),
            sa.column("number_hint", sa.Text()),
            sa.column("document_hint", sa.Text()),
        ),
        [
            {
                "scheme": seed.scheme,
                "country": seed.country,
                "id_type": seed.id_type,
                "label": seed.label,
                "validator": seed.validator,
                "requires_expiry": seed.requires_expiry,
                "input_mode": seed.input_mode,
                "number_hint": seed.number_hint,
                "document_hint": seed.document_hint,
            }
            for seed in IDENTITY_SCHEME_SEEDS
        ],
    )

    op.add_column(
        "kyc_applications",
        sa.Column("id_expiry_date", sa.Date(), nullable=True),
    )
    for column in _COUNTRY_COLUMNS:
        op.create_foreign_key(
            f"kyc_applications_{column}_fkey",
            "kyc_applications",
            "countries",
            [column],
            ["code"],
            ondelete="RESTRICT",
            postgresql_not_valid=True,
        )

    op.drop_constraint(
        "kyc_onboarding_requirements_when_valid",
        "kyc_onboarding_requirements",
        type_="check",
    )
    op.create_check_constraint(
        "kyc_onboarding_requirements_when_valid",
        "kyc_onboarding_requirements",
        _REQUIRED_WHEN_AFTER,
    )
    op.bulk_insert(
        _requirements,
        [
            {
                "step": seed.step,
                "name": seed.name,
                "kind": seed.kind,
                "required_when": seed.required_when,
                "copy_on_resubmit": seed.copy_on_resubmit,
            }
            for seed in ID_EXPIRY_REQUIREMENT_SEEDS
        ],
    )
    op.execute(
        _steps.update()
        .where(_steps.c.step == "id-document")
        .values(description=_ID_DOCUMENT_STEP_AFTER)
    )

    op.bulk_insert(
        _signals,
        [
            {
                "signal": seed.signal,
                "description": seed.description,
                "score_effect": seed.score_effect,
                "is_active": True,
            }
            for seed in JURISDICTION_RISK_SIGNAL_SEEDS
        ],
    )
    op.execute(
        _signals.update()
        .where(_signals.c.signal.in_(sorted(RETIRED_RISK_SIGNALS)))
        .values(is_active=False)
    )


def downgrade() -> None:
    op.execute(
        _signals.update()
        .where(_signals.c.signal.in_(sorted(RETIRED_RISK_SIGNALS)))
        .values(is_active=True)
    )
    # Fails, deliberately, once an assessment has fired a new signal: the audit
    # snapshot references it, and that history is not ours to delete.
    op.execute(
        _signals.delete().where(
            _signals.c.signal.in_(
                [seed.signal for seed in JURISDICTION_RISK_SIGNAL_SEEDS]
            )
        )
    )

    op.execute(
        _steps.update()
        .where(_steps.c.step == "id-document")
        .values(description=_ID_DOCUMENT_STEP_BEFORE)
    )
    op.execute(
        _requirements.delete().where(
            _requirements.c.required_when == "id_requires_expiry"
        )
    )
    op.drop_constraint(
        "kyc_onboarding_requirements_when_valid",
        "kyc_onboarding_requirements",
        type_="check",
    )
    op.create_check_constraint(
        "kyc_onboarding_requirements_when_valid",
        "kyc_onboarding_requirements",
        _REQUIRED_WHEN_BEFORE,
    )

    for column in reversed(_COUNTRY_COLUMNS):
        op.drop_constraint(
            f"kyc_applications_{column}_fkey",
            "kyc_applications",
            type_="foreignkey",
        )
    op.drop_column("kyc_applications", "id_expiry_date")

    op.drop_index(
        "uq_kyc_identity_schemes_one_fallback_per_type",
        table_name="kyc_identity_schemes",
        postgresql_where=sa.text("country IS NULL"),
        sqlite_where=sa.text("country IS NULL"),
    )
    op.drop_table("kyc_identity_schemes")
    op.drop_table("countries")
