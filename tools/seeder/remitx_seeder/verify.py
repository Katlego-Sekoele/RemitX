"""Business-rule checks over whatever is in the database.

The rules that matter most in RemitX live in Python, not in constraints: an
account balance equals the sum of its confirmed ledger rows, a remittance is
exactly seven legs that settle together, a pending deposit has no owner yet.
`verify` checks them over the whole database, so it is as useful against data
testers made by hand as against a seed run. A seed run always ends with it.

Each check reports `error` (a rule is broken), `warning` (worth a look, e.g.
a quote priced under a fee setting that has since changed) or `info`.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from remitx_seeder.settlement import SYNTHETIC_HASH_PREFIX

MAX_EXAMPLES = 5
REMITTANCE_LEGS = 7
CENT = Decimal("0.01")


@dataclass
class Finding:
    check: str
    severity: str
    ok: bool
    summary: str
    count: int = 0
    examples: list[str] = field(default_factory=list)


@dataclass
class VerifyReport:
    findings: list[Finding]

    @property
    def ok(self) -> bool:
        return all(f.ok for f in self.findings if f.severity == "error")

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error" and not f.ok]

    def as_dict(self) -> dict:
        return {"ok": self.ok, "findings": [asdict(f) for f in self.findings]}


def _finding(
    check: str, severity: str, problems: list[str], ok_summary: str, bad_summary: str
) -> Finding:
    ok = not problems
    return Finding(
        check=check,
        severity=severity,
        ok=ok,
        summary=ok_summary if ok else bad_summary.format(n=len(problems)),
        count=len(problems),
        examples=problems[:MAX_EXAMPLES],
    )


def check_balances(session) -> Finding:
    from remitx_api.models.orm.account import Account
    from remitx_api.models.orm.transaction import STATUS_CONFIRMED, Transaction
    from sqlalchemy import func, select

    credited = dict(
        session.execute(
            select(Transaction.debit_account_id, func.sum(Transaction.amount))
            .where(Transaction.status == STATUS_CONFIRMED)
            .group_by(Transaction.debit_account_id)
        ).all()
    )
    debited = dict(
        session.execute(
            select(Transaction.credit_account_id, func.sum(Transaction.amount))
            .where(Transaction.status == STATUS_CONFIRMED)
            .group_by(Transaction.credit_account_id)
        ).all()
    )
    problems = []
    for account in session.scalars(select(Account)).all():
        expected = Decimal(credited.get(account.account_id) or 0) - Decimal(
            debited.get(account.account_id) or 0
        )
        if Decimal(account.account_balance) != expected:
            problems.append(
                f"{account.reference or account.label}: balance "
                f"{account.account_balance} but confirmed rows sum to {expected}"
            )
    return _finding(
        "ledger.balances",
        "error",
        problems,
        "Every account balance equals its confirmed ledger rows",
        "{n} account balance(s) disagree with their confirmed ledger rows",
    )


def check_remittances(session) -> list[Finding]:
    from remitx_api.models.orm.account import CURRENCY_TOKEN
    from remitx_api.models.orm.quote import STATUS_USED, Quote
    from remitx_api.models.orm.remittance import Remittance
    from remitx_api.models.orm.transaction import (
        STATUS_CONFIRMED,
        TYPE_BENEFICIARY_PAYOUT,
        TYPE_FEE,
        TYPE_REMITTANCE,
        TYPE_TOKEN_BURN,
        Transaction,
    )
    from sqlalchemy import select

    legs_by_quote: dict = defaultdict(list)
    for leg in session.scalars(
        select(Transaction).where(Transaction.quote_id.is_not(None))
    ).all():
        legs_by_quote[leg.quote_id].append(leg)

    shape, amounts, status_problems = [], [], []
    remitted = set()
    for remittance, quote in session.execute(
        select(Remittance, Quote).join(Quote, Quote.quote_id == Remittance.quote_id)
    ).all():
        remitted.add(quote.quote_id)
        legs = legs_by_quote.get(quote.quote_id, [])
        label = f"remittance {remittance.remittance_id}"
        if len(legs) != REMITTANCE_LEGS:
            shape.append(f"{label}: {len(legs)} legs, expected {REMITTANCE_LEGS}")
            continue
        statuses = {leg.status for leg in legs}
        if len(statuses) != 1:
            status_problems.append(
                f"{label}: legs disagree ({', '.join(sorted(statuses))})"
            )
        if quote.status != STATUS_USED:
            status_problems.append(f"{label}: its quote is {quote.status}, not USED")
        burn = [leg for leg in legs if leg.type == TYPE_TOKEN_BURN]
        if len(burn) != 1:
            shape.append(f"{label}: {len(burn)} burn legs")
            continue
        confirmed = statuses == {STATUS_CONFIRMED}
        if confirmed != bool(burn[0].xrpl_tx_hash):
            status_problems.append(
                f"{label}: burn hash {'missing' if confirmed else 'present'} "
                f"on a {burn[0].status} group"
            )
        fee_margin = quote.sender_transaction_fee + quote.exchange_rate_margin
        expected = {
            (TYPE_FEE, quote.sender_currency): [fee_margin],
            (TYPE_REMITTANCE, quote.sender_currency): [
                quote.sender_amount - fee_margin
            ],
            (TYPE_REMITTANCE, CURRENCY_TOKEN): [quote.token_amount] * 3,
            (TYPE_TOKEN_BURN, CURRENCY_TOKEN): [quote.token_amount],
            (TYPE_BENEFICIARY_PAYOUT, quote.receiver_currency): [quote.receiver_amount],
        }
        actual: dict = defaultdict(list)
        for leg in legs:
            actual[(leg.type, leg.currency)].append(Decimal(leg.amount))
        for key, values in expected.items():
            if sorted(Decimal(v) for v in values) != sorted(actual.get(key, [])):
                amounts.append(
                    f"{label}: {key[0]} {key[1]} legs {actual.get(key)} "
                    f"!= quote {values}"
                )
                break

    orphan = [
        f"quote {quote_id}: {len(legs)} ledger rows but no remittance"
        for quote_id, legs in legs_by_quote.items()
        if quote_id not in remitted
    ]
    used = [
        f"quote {quote_id} is USED with no remittance"
        for quote_id in session.scalars(
            select(Quote.quote_id).where(Quote.status == STATUS_USED)
        ).all()
        if quote_id not in remitted
    ]
    return [
        _finding(
            "remittances.shape",
            "error",
            shape + orphan,
            "Every remittance has exactly seven legs, and every leg a remittance",
            "{n} remittance(s) with the wrong legs",
        ),
        _finding(
            "remittances.status",
            "error",
            status_problems + used,
            "Remittance legs settle together; burn hashes only on confirmed groups",
            "{n} remittance(s) whose legs or quote disagree",
        ),
        _finding(
            "remittances.amounts",
            "error",
            amounts,
            "Every leg's amount matches its frozen quote",
            "{n} remittance(s) whose legs do not match the quote",
        ),
    ]


def check_quote_pricing(session) -> Finding:
    """Quotes priced under the fee settings in force now. A mismatch is a
    warning, not an error: the settings may have changed since."""
    from remitx_api.config import Config
    from remitx_api.models.orm.quote import Quote
    from sqlalchemy import select

    problems = []
    for quote in session.scalars(
        select(Quote).where(Quote.sender_currency == "ZAR")
    ).all():
        amount = Decimal(quote.sender_amount)
        fee = (Config.FIXED_FEE_ZAR + Config.PERCENTAGE_FEE_RATE * amount).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
        margin = (Config.FX_MARGIN_RATE * amount).quantize(CENT, rounding=ROUND_HALF_UP)
        if fee != Decimal(quote.sender_transaction_fee) or margin != Decimal(
            quote.exchange_rate_margin
        ):
            problems.append(
                f"quote {quote.quote_id}: fee {quote.sender_transaction_fee} / margin "
                f"{quote.exchange_rate_margin}, current settings give {fee} / {margin}"
            )
    return _finding(
        "quotes.fee_model",
        "warning",
        problems,
        "Every ZAR quote matches the current fee settings",
        "{n} quote(s) priced under different fee settings",
    )


def check_deposits(session) -> Finding:
    from remitx_api.models.orm.deposit import Deposit
    from remitx_api.models.orm.transaction import (
        STATUS_CONFIRMED,
        STATUS_PENDING,
        Transaction,
    )
    from sqlalchemy import select

    problems = []
    for deposit, tx in session.execute(
        select(Deposit, Transaction).join(
            Transaction, Transaction.tx_id == Deposit.tx_id
        )
    ).all():
        label = f"deposit {deposit.deposit_id} ({deposit.user_account_reference})"
        if tx.status == STATUS_PENDING:
            if deposit.user_id or deposit.confirmed_by or tx.debit_account_id:
                problems.append(f"{label}: pending but already has an owner")
        elif tx.status == STATUS_CONFIRMED:
            if not (deposit.user_id and deposit.confirmed_by and tx.debit_account_id):
                problems.append(f"{label}: confirmed without an owner or confirmer")
        else:
            problems.append(f"{label}: transaction is {tx.status}")
    return _finding(
        "deposits.state",
        "error",
        problems,
        "Pending deposits have no owner; confirmed ones have owner and confirmer",
        "{n} deposit(s) in an inconsistent state",
    )


def check_kyc(session) -> list[Finding]:
    from remitx_api.models.orm.kyc_application import KycApplication
    from remitx_api.models.orm.kyc_application_history import KycApplicationHistory
    from sqlalchemy import select

    latest: dict = {}
    for row in session.scalars(
        select(KycApplicationHistory).order_by(
            KycApplicationHistory.application_id, KycApplicationHistory.version_after
        )
    ).all():
        latest[row.application_id] = row
    history, approved = [], []
    for application in session.scalars(select(KycApplication)).all():
        label = f"application {application.application_id}"
        row = latest.get(application.application_id)
        if row is not None and row.status != application.status:
            history.append(
                f"{label}: status {application.status}, last history row {row.status}"
            )
        if application.status == "approved" and not (
            application.tier_granted
            and application.risk_rating
            and application.next_review_at
        ):
            approved.append(f"{label}: approved without tier, rating or next review")
    return [
        _finding(
            "kyc.history",
            "error",
            history,
            "Every application's status matches its latest history row",
            "{n} application(s) disagree with their history",
        ),
        _finding(
            "kyc.approvals",
            "error",
            approved,
            "Every approval carries a tier, a risk rating and a next review date",
            "{n} approval(s) missing a tier, rating or review date",
        ),
    ]


def check_user_accounts(session) -> Finding:
    from remitx_api.models.orm.account import (
        CURRENCY_TOKEN,
        CURRENCY_ZAR,
        TYPE_USER,
        Account,
        create_account_reference,
    )
    from remitx_api.models.orm.user import User
    from sqlalchemy import select

    held: dict = defaultdict(dict)
    for account in session.scalars(
        select(Account).where(Account.type == TYPE_USER)
    ).all():
        held[account.user_id][account.account_currency] = account.reference
    problems = []
    for user in session.scalars(select(User)).all():
        for currency in (CURRENCY_ZAR, CURRENCY_TOKEN):
            reference = held[user.id].get(currency)
            expected = create_account_reference(user.base_reference, currency)
            if reference != expected:
                problems.append(
                    f"{user.base_reference}: {currency} account {reference!r}, "
                    f"expected {expected!r}"
                )
    return _finding(
        "users.accounts",
        "error",
        problems,
        "Every user holds ZAR and uctusd accounts named from their base reference",
        "{n} missing or misnamed user account(s)",
    )


def check_beneficiaries(session) -> Finding:
    from remitx_api.models.orm.account import TYPE_USER, Account
    from remitx_api.models.orm.beneficiary import Beneficiary
    from sqlalchemy import select

    held = {
        (user_id, currency)
        for user_id, currency in session.execute(
            select(Account.user_id, Account.account_currency).where(
                Account.type == TYPE_USER
            )
        ).all()
    }
    problems = [
        f"beneficiary {b.beneficiary_id}: recipient holds no "
        f"{b.payout_currency} account"
        for b in session.scalars(select(Beneficiary)).all()
        if (b.linked_user_id, b.payout_currency) not in held
    ]
    return _finding(
        "beneficiaries.payout_account",
        "error",
        problems,
        "Every beneficiary's recipient holds an account in the payout currency",
        "{n} beneficiary(ies) with no payout account",
    )


def synthetic_hash_summary(session) -> Finding:
    from remitx_api.models.orm.transaction import TYPE_TOKEN_BURN, Transaction
    from sqlalchemy import func, select

    total = session.scalar(
        select(func.count()).where(
            Transaction.type == TYPE_TOKEN_BURN, Transaction.xrpl_tx_hash.is_not(None)
        )
    )
    synthetic = session.scalar(
        select(func.count()).where(
            Transaction.type == TYPE_TOKEN_BURN,
            Transaction.xrpl_tx_hash.like(f"{SYNTHETIC_HASH_PREFIX}%"),
        )
    )
    return Finding(
        check="xrpl.synthetic_hashes",
        severity="info",
        ok=True,
        summary=f"{synthetic} of {total} burn hashes are synthetic (seeded, "
        "not on the XRPL; they start 5EED)",
        count=synthetic or 0,
    )


def check_treasury_on_chain(session) -> Finding:
    """The treasury's ledger balance against its real on-chain balance. Needs
    PLATFORM_WALLET_ADDRESS and network access to the XRPL testnet."""
    import os

    from remitx_api.config import Config
    from remitx_api.repositories.account_repository import AccountRepository
    from remitx_api.services.remittance_service import REMITX_TREASURY_WALLET_LABEL
    from xrpl.clients import JsonRpcClient
    from xrpl.models.requests import AccountLines

    address = os.environ.get("PLATFORM_WALLET_ADDRESS", "")
    if not address:
        return Finding(
            "treasury.on_chain",
            "info",
            True,
            "Skipped: PLATFORM_WALLET_ADDRESS is not set",
        )
    treasury = AccountRepository().get_platform_account_by_label(
        REMITX_TREASURY_WALLET_LABEL
    )
    config = Config()
    lines = (
        JsonRpcClient(config.XRPL_TESTNET_URL)
        .request(
            AccountLines(
                account=address, peer=config.UCTUSD_ISSUER, ledger_index="validated"
            )
        )
        .result.get("lines", [])
    )
    on_chain = next(
        (
            Decimal(line["balance"])
            for line in lines
            if line["currency"] == config.UCTUSD_CURRENCY_CODE_HEX
        ),
        Decimal("0"),
    )
    ledger = Decimal(treasury.account_balance) if treasury else Decimal("0")
    ok = ledger == on_chain
    return Finding(
        "treasury.on_chain",
        "warning",
        ok,
        f"Treasury ledger {ledger} uctusd, on chain {on_chain}"
        + ("" if ok else " (differ)"),
    )


def run_verify(session, *, check_chain: bool = False) -> VerifyReport:
    findings = [check_balances(session)]
    findings += check_remittances(session)
    findings.append(check_quote_pricing(session))
    findings.append(check_deposits(session))
    findings += check_kyc(session)
    findings.append(check_user_accounts(session))
    findings.append(check_beneficiaries(session))
    findings.append(synthetic_hash_summary(session))
    if check_chain:
        try:
            findings.append(check_treasury_on_chain(session))
        except Exception as exc:  # noqa: BLE001 — network trouble is not a rule break
            findings.append(
                Finding(
                    "treasury.on_chain",
                    "info",
                    True,
                    f"Skipped: {type(exc).__name__}: {exc}",
                )
            )
    return VerifyReport(findings)
