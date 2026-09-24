"""The live schema, and how much of it the seeder fills.

Read from the target database (not from the ORM), so it shows what is really
there. For each table: its row count, which story writes it, and the columns
that are NULL in every row. A table no story writes, or a column always NULL,
is the sign that the schema moved on and the seeder has not caught up yet.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# Which part of the seeder writes each table. Tables owned by migrations
# (reference data) are marked as such. Anything missing from this map shows
# up as "no generator" on the coverage page.
COVERAGE = {
    "users": "people",
    "accounts": "people (signup) · direct.open_payout_account",
    "user_roles": "people (staff grants)",
    "kyc_applications": "kyc",
    "kyc_application_history": "kyc",
    "kyc_decisions": "kyc",
    "kyc_decision_history": "kyc",
    "kyc_documents": "kyc (SPECIMEN documents)",
    "kyc_assessment_audit": "kyc (risk scoring on submit)",
    "kyc_assessment_audit_signals": "kyc (risk scoring on submit)",
    "audit_log": "kyc · people (written by the backend)",
    "beneficiaries": "money",
    "deposits": "money (bank statements)",
    "transactions": "money · settlement · direct.record_treasury_top_up",
    "quotes": "money",
    "remittances": "money",
    "exchange_rates": "money (historical rate provider)",
}

REFERENCE_TABLES = {
    "alembic_version",
    "countries",
    "kyc_application_status_progressions",
    "kyc_application_statuses",
    "kyc_identity_schemes",
    "kyc_onboarding_editable_statuses",
    "kyc_onboarding_requirements",
    "kyc_onboarding_steps",
    "kyc_pep_relationships",
    "kyc_reason_codes",
    "kyc_risk_ratings",
    "kyc_risk_signals",
    "kyc_tiers",
    "permissions",
    "role_permissions",
    "roles",
    "toxic_combinations",
}

# Tables that exist but carry no domain data the seeder should make.
IGNORED_TABLES = {
    "integration_messages": "throwaway smoke-test table",
}


@dataclass
class TableCoverage:
    table: str
    rows: int
    columns: int
    kind: str  # seeded | reference | ignored | uncovered
    written_by: str
    always_null: list[str]


def describe(session) -> list[TableCoverage]:
    from sqlalchemy import inspect, text

    inspector = inspect(session.get_bind())
    tables = []
    for name in sorted(inspector.get_table_names()):
        columns = [column["name"] for column in inspector.get_columns(name)]
        quoted = session.get_bind().dialect.identifier_preparer.quote
        counts = session.execute(
            text(
                "SELECT count(*) AS total, "
                + ", ".join(
                    f"count({quoted(c)}) AS c{i}" for i, c in enumerate(columns)
                )
                + f" FROM {quoted(name)}"
            )
        ).one()
        total = counts[0]
        always_null = (
            [c for i, c in enumerate(columns) if counts[i + 1] == 0] if total else []
        )
        if name in REFERENCE_TABLES:
            kind, written_by = "reference", "migrations"
        elif name in IGNORED_TABLES:
            kind, written_by = "ignored", IGNORED_TABLES[name]
        elif name in COVERAGE:
            kind, written_by = "seeded", COVERAGE[name]
        else:
            kind, written_by = "uncovered", "no generator yet"
        tables.append(
            TableCoverage(name, total, len(columns), kind, written_by, always_null)
        )
    return tables


def as_dicts(tables: list[TableCoverage]) -> list[dict]:
    return [asdict(t) for t in tables]
