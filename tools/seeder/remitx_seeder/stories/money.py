"""Money moving: beneficiaries, cash-in, and sends.

- **Beneficiaries** are added through `BeneficiaryController.create`, for
  recipients drawn from the sender's corridor.
- **Cash-in** is a bank statement. Each deposit is a line on that day's
  statement, and the next working morning the reconciliation job
  (`deposit_service.process_deposits`) runs over it, as the admin page does.
  Some people mistype their reference; those lines land pending, and a treasury
  operator resolves most of them a day or two later through
  `approve_pending_deposit`. Statements also carry a few outgoing lines, which
  reconciliation skips.
- **Sends** are a quote (`QuoteController`) and, a few minutes later, its
  confirmation (`RemittanceController.confirm`), within the sender's KYC
  limits and available balance. Some quotes are left to expire. Settlement is
  in settlement.py.
- **Payout accounts** in a currency other than ZAR are opened by the
  recipient through `AccountController.open_account` once they are verified.
  Someone who cannot pass KYC (no residence in a country RemitX onboards) is
  provisioned in `direct.open_payout_account`, because a quote now refuses a
  beneficiary who does not already hold the payout currency.
- **Cash-out** is an external bank account (`BankAccountController`) that a
  payout operator verifies or rejects, then a withdrawal
  (`WithdrawalController.request`) of spare balance.
"""

from __future__ import annotations

import string
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import ROUND_UP, Decimal

from remitx_seeder import direct
from remitx_seeder.context import RunContext, SeededPerson
from remitx_seeder.data import load
from remitx_seeder.generators.personas import weighted
from remitx_seeder.sim import Simulation
from remitx_seeder.stories.timing import SAST, business_time, paydays, waking_time

MIN_SEND_ZAR = Decimal("150")
# Payout currency a verified person opens for themselves. ZAR already exists
# from signup. Zimbabwean and Namibian recipients are not in this map's
# onboarding countries, so they never reach `open_account`.
HOME_PAYOUT = {"US": "USD", "ZW": "USD", "NA": "NAD"}
REJECT_REASONS = (
    "Account holder name does not match the profile.",
    "Branch code does not match the bank.",
    "The statement is older than three months.",
)
# What a send costs on top of the amount, roughly (fixed + percentage + FX
# margin). Only used to size deposits, never to price anything.
FEE_BUFFER_RATE = Decimal("0.03")
FEE_BUFFER_FIXED = Decimal("20")


def round_send(amount: Decimal) -> Decimal:
    """People send round numbers: R50s below R1,000, R100s above."""
    step = Decimal("50") if amount < 1000 else Decimal("100")
    return max(MIN_SEND_ZAR, (amount / step).quantize(Decimal("1")) * step)


def floor_send(amount: Decimal) -> Decimal:
    """The largest round amount (as `round_send` counts round) not above
    `amount`."""
    step = Decimal("50") if amount < 1000 else Decimal("100")
    return (amount // step) * step


def typo(ctx: RunContext, reference: str) -> str:
    """How people get a deposit reference wrong."""
    base, _, suffix = reference.partition("-")
    kind = ctx.rng.choice(["no_hyphen", "upper", "no_suffix", "transposed", "name"])
    if kind == "no_hyphen":
        return f"{base}{suffix}"
    if kind == "upper":
        return reference.upper()
    if kind == "no_suffix":
        return base
    if kind == "transposed":
        # Only neighbours that differ: swapping "nn" in "anna1" changes nothing.
        spots = [i for i in range(len(base) - 1) if base[i] != base[i + 1]]
        if spots:
            chars = list(base)
            i = ctx.rng.choice(spots)
            chars[i], chars[i + 1] = chars[i + 1], chars[i]
            return f"{''.join(chars)}-{suffix}"
        return f"{base}{suffix}"
    return base.rstrip(string.digits).upper() + " REMITX"


class MoneyStory:
    def __init__(self, ctx: RunContext, sim: Simulation) -> None:
        self.ctx = ctx
        self.sim = sim
        self._statement_lines: dict[date, list[dict]] = defaultdict(list)
        self._reconciliation_scheduled: set[date] = set()

    # --- the verified sender's life --------------------------------------

    def on_verified(self, person: SeededPerson) -> None:
        self._open_home_payout_account(person)
        self._plan_bank_account(person)
        if person.persona.role != "sender":
            return
        if self.ctx.rng.random() < self.ctx.scenario.money.dormant_rate:
            self.ctx.count("money.dormant_senders")
            return
        at = self.ctx.clock.now() + timedelta(hours=self.ctx.rng.uniform(0.2, 30))
        self.sim.schedule(
            at, "beneficiary.add", lambda: self._add_beneficiaries(person)
        )
        self._plan_deposits(person)

    def _add_beneficiaries(self, person: SeededPerson) -> None:
        corridor = person.persona.corridor
        wanted = self.ctx.rng.randint(*corridor["beneficiaries"])
        pool = [
            p
            for p in self.ctx.people_with_role("recipient")
            if p.persona.nationality == corridor["recipient_country"]
            and p.user_id is not None
            and p.user_id != person.user_id
            and all(b["user_id"] != p.user_id for b in person.beneficiaries)
        ]
        if not pool:
            # Nobody from home has signed up yet; try again tomorrow.
            self.sim.schedule(
                self.ctx.clock.now() + timedelta(days=1),
                "beneficiary.add",
                lambda: self._add_beneficiaries(person),
            )
            return
        for recipient in self.ctx.rng.sample(pool, k=min(wanted, len(pool))):
            self._add_beneficiary(person, recipient)

    def _add_beneficiary(self, person: SeededPerson, recipient: SeededPerson) -> None:
        from remitx_api.controllers.beneficiary_controller import BeneficiaryController

        corridor = person.persona.corridor
        currency = weighted(self.ctx.rng, corridor["payout_currencies"])
        self._ensure_payout_account(recipient, currency)
        row = BeneficiaryController().create(
            person.user_id,
            recipient.user_id,
            currency,
            weighted(self.ctx.rng, corridor["relationships"]),
        )
        person.beneficiaries.append(
            {
                "beneficiary_id": row.beneficiary.beneficiary_id,
                "user_id": recipient.user_id,
                "currency": currency,
            }
        )
        self.ctx.count("money.beneficiaries")

    def _open_home_payout_account(self, person: SeededPerson) -> None:
        currency = HOME_PAYOUT.get(person.persona.nationality)
        if currency is None:
            return
        self._ensure_payout_account(person, currency)

    def _ensure_payout_account(self, person: SeededPerson, currency: str) -> None:
        """The beneficiary must already hold `currency` before a quote.

        A verified customer opens it themselves. Anyone else is provisioned
        directly: the product refuses `open_account` until KYC is approved,
        and people outside the onboarding countries never get there.
        """
        from remitx_api.errors.accounts import AccountAlreadyHeldError
        from remitx_api.models.orm.account import CURRENCY_ZAR
        from remitx_api.repositories.account_repository import AccountRepository

        if currency == CURRENCY_ZAR:
            return
        if AccountRepository().get_user_account(person.user_id, currency) is not None:
            return
        if person.verified:
            from remitx_api.controllers.account_controller import AccountController

            try:
                AccountController().open_account(person.user_id, currency)
            except AccountAlreadyHeldError:
                return
            self.ctx.count("money.payout_accounts_opened")
            return
        direct.open_payout_account(person.user_id, person.base_reference, currency)
        self.ctx.count("money.payout_accounts_provisioned")

    # --- cash-out ----------------------------------------------------------

    def _plan_bank_account(self, person: SeededPerson) -> None:
        money = self.ctx.scenario.money
        if self.ctx.rng.random() >= money.bank_account_rate:
            return
        person.will_cash_out = self.ctx.rng.random() < money.withdraw_rate
        currency = (
            "ZAR"
            if person.persona.role == "sender"
            else HOME_PAYOUT.get(person.persona.nationality, "ZAR")
        )
        at = self.ctx.clock.now() + timedelta(hours=self.ctx.rng.uniform(1, 8))
        self.sim.schedule(
            at, "cashout.bank_account", lambda: self._add_bank_account(person, currency)
        )

    def _add_bank_account(self, person: SeededPerson, currency: str) -> None:
        from remitx_api.controllers.bank_account_controller import (
            BankAccountController,
        )

        banks = load("banks")[currency]
        bank = self.ctx.rng.choice(banks)
        holder = f"{person.persona.first_name} {person.persona.last_name}"
        view = BankAccountController().add(
            person.user_id,
            holder,
            bank["name"],
            str(self.ctx.rng.randint(10**9, 10**10 - 1)),
            currency,
            bank.get("branch_code"),
            person.persona.residence or person.persona.nationality,
        )
        record = {
            "id": view.bank_account_id,
            "currency": currency,
            "status": "pending_verification",
        }
        person.bank_accounts.append(record)
        self.ctx.count("cashout.bank_accounts")

        money = self.ctx.scenario.money
        roll = self.ctx.rng.random()
        if roll < money.bank_reject_rate:
            action = "reject"
        elif roll < money.bank_reject_rate + money.bank_leave_pending_rate:
            self.ctx.count("cashout.bank_accounts_left_pending")
            return
        else:
            action = "verify"
        at = business_time(
            self.ctx.rng,
            self.ctx.clock.now() + timedelta(hours=self.ctx.rng.uniform(1, 8)),
        )
        self.sim.schedule(
            at,
            f"cashout.bank_account.{action}",
            lambda: self._review_bank_account(person, record, action),
        )

    def _review_bank_account(
        self, person: SeededPerson, record: dict, action: str
    ) -> None:
        from remitx_api.controllers.bank_account_controller import (
            BankAccountController,
        )

        operators = self.ctx.staff_by_role.get("payout_operator") or []
        if not operators:
            self.ctx.count("cashout.no_operator")
            return
        operator = self.ctx.rng.choice(operators)
        controller = BankAccountController()
        if action == "reject":
            controller.reject(
                record["id"],
                operator.user_id,
                self.ctx.rng.choice(REJECT_REASONS),
            )
            record["status"] = "rejected"
            self.ctx.count("cashout.bank_accounts_rejected")
            return
        controller.verify(record["id"], operator.user_id)
        record["status"] = "verified"
        self.ctx.count("cashout.bank_accounts_verified")
        if person.will_cash_out:
            currency = "ZAR" if person.persona.role == "sender" else record["currency"]
            self._withdraw(person, currency)

    def _withdraw(self, person: SeededPerson, currency: str) -> None:
        from remitx_api.controllers.withdrawal_controller import WithdrawalController
        from remitx_api.models.orm.account import CURRENCY_ZAR
        from remitx_api.repositories.account_repository import AccountRepository

        if person.cashed_out:
            return
        verified = [
            row
            for row in person.bank_accounts
            if row["status"] == "verified" and row["currency"] == currency
        ]
        if not verified:
            self.ctx.count("cashout.waiting_on_bank")
            return
        accounts = AccountRepository()
        account = accounts.get_user_account(person.user_id, currency)
        if account is None:
            return
        available = accounts.get_available_balance(account.account_id)
        # Senders keep a minimum send; everyone else just leaves a small sum.
        floor = MIN_SEND_ZAR if currency == CURRENCY_ZAR else Decimal("20")
        spare = available - floor
        if spare < Decimal("50"):
            self.ctx.count("cashout.skipped_low_balance")
            return
        # Capped so a withdrawal before the month's sends does not eat the
        # cash-in those sends were sized from. The deposit plan adds R250
        # when this person will cash out.
        amount = min(spare, Decimal(self.ctx.rng.randint(80, 200)))
        WithdrawalController().request(
            person.user_id, verified[0]["id"], currency, amount
        )
        person.cashed_out = True
        self.ctx.count("cashout.withdrawals")

    # --- cash-in -----------------------------------------------------------

    def _plan_deposits(self, person: SeededPerson) -> None:
        start = (self.ctx.clock.now() + timedelta(days=1)).astimezone(SAST).date()
        end = self.ctx.window_end.astimezone(SAST).date()
        kind = person.persona.payday or "25th"
        days = paydays(kind, start, end)
        if kind == "weekly_friday":
            # Weekly earners still send monthly, from the last pay of the month.
            by_month: dict[tuple[int, int], date] = {}
            for day in days:
                by_month[(day.year, day.month)] = day
            days = sorted(by_month.values())
        if not days:
            # Verified after this month's payday: a first deposit soon anyway.
            days = [start + timedelta(days=self.ctx.rng.randint(0, 4))]
        corridor = person.persona.corridor
        for day in days:
            budget = Decimal(self.ctx.rng.randint(*corridor["monthly_send_zar"]))
            sends = self.ctx.rng.randint(*corridor["sends_per_month"])
            amounts = self._split(budget, sends)
            needed = sum(amounts) * (1 + FEE_BUFFER_RATE) + FEE_BUFFER_FIXED * sends
            # Cash-out takes a slice after the sends; leave that on top of
            # the fee buffer so the transfers still fit.
            if person.will_cash_out:
                needed += Decimal("250")
            # Up to the next R50: people deposit round-ish amounts.
            deposit = (
                needed * Decimal(str(self.ctx.scenario.money.deposit_headroom)) / 50
            ).quantize(Decimal("1"), rounding=ROUND_UP) * 50
            moment = waking_time(self.ctx.rng, day)
            reference = person.zar_reference
            mistyped = (
                self.ctx.rng.random() < self.ctx.scenario.money.reference_typo_rate
            )
            if mistyped:
                reference = typo(self.ctx, reference)
            self._add_statement_line(
                moment,
                {
                    "reference": reference,
                    "amount": deposit,
                    "person": person,
                    "sends": amounts,
                    "mistyped": mistyped,
                },
            )

    def _split(self, budget: Decimal, parts: int) -> list[Decimal]:
        weights = [self.ctx.rng.uniform(0.6, 1.4) for _ in range(parts)]
        total = sum(weights)
        return [round_send(budget * Decimal(str(w / total))) for w in weights]

    def _add_statement_line(self, moment: datetime, line: dict) -> None:
        day = moment.astimezone(SAST).date()
        line["moment"] = moment
        self._statement_lines[day].append(line)
        if day in self._reconciliation_scheduled:
            return
        self._reconciliation_scheduled.add(day)
        run_at = business_time(
            self.ctx.rng,
            datetime.combine(day + timedelta(days=1), datetime.min.time(), SAST),
        )
        self.sim.schedule(run_at, "deposits.reconcile", lambda: self._reconcile(day))

    def _reconcile(self, day: date) -> None:
        from remitx_api.models.orm.transaction import STATUS_CONFIRMED
        from remitx_api.repositories.transaction_repository import (
            TransactionRepository,
        )
        from remitx_api.services import deposit_service

        lines = self._statement_lines.pop(day, [])
        rows = [
            {
                "date": line["moment"].isoformat(),
                "reference": line["reference"],
                "amount": str(line["amount"]),
                "currency": "ZAR",
            }
            for line in lines
        ]
        # Real statements mix RemitX's own outgoing payments in; the job
        # skips them.
        if self.ctx.rng.random() < 0.3:
            rows.append(
                {
                    "date": waking_time(self.ctx.rng, day).isoformat(),
                    "reference": "BANK CHARGES",
                    "amount": str(-Decimal(self.ctx.rng.randint(35, 180))),
                    "currency": "ZAR",
                }
            )
        operator = self.ctx.staff("treasury_operator")
        result = deposit_service.process_deposits(rows, actor_user_id=operator.user_id)
        self.ctx.count("deposits.statement_lines", len(rows))
        self.ctx.count("deposits.skipped_lines", len(result.skipped))
        transactions = TransactionRepository()
        by_reference = {
            (
                deposit.user_account_reference,
                transactions.get_by_id(deposit.tx_id).amount,
            ): deposit
            for deposit in result.deposits
        }
        for line in lines:
            deposit = by_reference.get((line["reference"], line["amount"]))
            if deposit is None:
                continue
            status = transactions.get_by_id(deposit.tx_id).status
            if status == STATUS_CONFIRMED:
                self.ctx.count("deposits.matched")
                self._credited(line)
            else:
                self.ctx.count("deposits.pending")
                self._maybe_resolve(deposit.deposit_id, line)

    def _maybe_resolve(self, deposit_id, line: dict) -> None:
        if self.ctx.rng.random() >= self.ctx.scenario.money.resolve_pending_rate:
            self.ctx.count("deposits.left_pending")
            return
        at = business_time(
            self.ctx.rng,
            self.ctx.clock.now() + timedelta(hours=self.ctx.rng.uniform(3, 60)),
        )

        def resolve() -> None:
            from remitx_api.services import deposit_service

            operator = self.ctx.staff("treasury_operator")
            deposit_service.approve_pending_deposit(
                deposit_id, line["person"].zar_reference, operator.user_id
            )
            self.ctx.count("deposits.resolved_by_operator")
            self._credited(line)

        self.sim.schedule(at, "deposits.resolve", resolve)

    # --- sends -------------------------------------------------------------

    def _credited(self, line: dict) -> None:
        person: SeededPerson = line["person"]
        cursor = self.ctx.clock.now()
        for amount in line["sends"]:
            cursor += timedelta(days=self.ctx.rng.uniform(0, 6))
            at = waking_time(self.ctx.rng, cursor.astimezone(SAST).date())
            if at < self.ctx.clock.now():
                at = self.ctx.clock.now() + timedelta(hours=self.ctx.rng.uniform(1, 6))
            self.sim.schedule(
                at,
                "send.quote",
                lambda amount=amount: self._quote(person, amount),
            )
        # Cash out from this deposit while it is still intact. Sends are
        # scheduled over the following days; the amount is capped under the
        # reserve _plan_deposits added.
        self._cash_out_from_deposit(person)

    def _cash_out_from_deposit(self, person: SeededPerson) -> None:
        """Withdraw spare salary, opening a bank account first if needed.

        Until one withdrawal has landed, every credited sender tries. After
        that, only people who already decided to cash out do.
        """
        if person.cashed_out:
            return
        if not person.will_cash_out and self.ctx.counters.get("cashout.withdrawals", 0):
            return
        person.will_cash_out = True
        zar = [
            row
            for row in person.bank_accounts
            if row["currency"] == "ZAR" and row["status"] != "rejected"
        ]
        if not zar:
            self._add_bank_account(person, "ZAR")
            return
        if any(row["status"] == "verified" for row in zar):
            self._withdraw(person, "ZAR")

    def _quote(self, person: SeededPerson, wanted: Decimal) -> None:
        from remitx_api.controllers.quote_controller import QuoteController
        from remitx_api.models.orm.account import CURRENCY_ZAR
        from remitx_api.repositories.account_repository import AccountRepository
        from remitx_api.repositories.kyc_application_repository import (
            KycApplicationRepository,
        )

        if not person.beneficiaries:
            self.ctx.count("send.no_beneficiary")
            return
        standing = KycApplicationRepository().get_standing(person.user_id)
        now = self.ctx.clock.now()
        accounts = AccountRepository()
        zar = accounts.get_user_account(person.user_id, CURRENCY_ZAR)
        # What the API will let them send: what's left of today's and this
        # month's allowance (SAST, counting sends still settling) and their
        # available balance.
        room = min(
            wanted,
            standing.daily_remaining_zar,
            standing.monthly_remaining_zar,
            accounts.get_available_balance(zar.account_id),
        )
        amount = min(wanted, floor_send(room))
        if amount < MIN_SEND_ZAR:
            self.ctx.count("send.skipped_no_room")
            return
        beneficiary = self.ctx.rng.choices(
            person.beneficiaries,
            weights=[3] + [1] * (len(person.beneficiaries) - 1),
        )[0]
        quote = QuoteController().create_quote(
            sender_user_id=person.user_id,
            beneficiary_id=beneficiary["beneficiary_id"],
            sender_amount=amount,
            sender_currency=CURRENCY_ZAR,
            receiver_payout_currency=beneficiary["currency"],
        )
        self.ctx.count("send.quotes")
        if self.ctx.rng.random() < self.ctx.scenario.money.quote_abandon_rate:
            self.ctx.count("send.quotes_abandoned")
            if self.ctx.rng.random() < 0.5:
                # Came back later the same day and went ahead.
                self.sim.schedule(
                    now + timedelta(hours=self.ctx.rng.uniform(1, 5)),
                    "send.quote",
                    lambda: self._quote(person, wanted),
                )
            return
        quote_id = quote.quote_id
        confirm_at = now + timedelta(minutes=self.ctx.rng.uniform(0.5, 8))
        self.sim.schedule(
            confirm_at,
            "send.confirm",
            lambda: self._confirm(person, quote_id, amount),
        )

    def _confirm(self, person: SeededPerson, quote_id, amount: Decimal) -> None:
        from remitx_api.controllers.remittance_controller import RemittanceController
        from remitx_api.repositories.kyc_application_repository import (
            KycApplicationRepository,
        )

        standing = KycApplicationRepository().get_standing(person.user_id)
        if amount > min(standing.daily_remaining_zar, standing.monthly_remaining_zar):
            # Another of their sends was confirmed after this quote was sized
            # and took the room it was sized for. Confirming would be refused,
            # so, like someone the app has told as much, they let it lapse.
            self.ctx.count("send.quotes_over_limit")
            return
        RemittanceController().confirm(person.user_id, quote_id)
        self.ctx.count("send.remittances")
