"""A few real settlements, end to end, after the replay.

Everything else in a seed run settles against a simulated chain. The live tail
proves the real pipeline still works: for up to N verified senders with a
Clerk account and a beneficiary, it

1. tops up their ZAR balance if needed, with a bank-statement line through the
   reconciliation job (in-process, like any other deposit);
2. signs in as them with a Clerk session token (development instances allow
   the Backend API to open one);
3. calls the target's real API: `POST /quotes`, then `POST /remittances`;
4. polls `GET /remittances/{id}` while the real worker settles it on the XRPL
   testnet, and records the real hash.

It runs on the real clock, and it stops before a quote would take the run's
burns past `live_token_budget` uctusd: the treasury is funded by the lecturer
and RemitX cannot replace what it burns.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from remitx_seeder.context import RunContext, SeededPerson

SEND_ZAR = Decimal("200")
POLL_SECONDS = 4
# A cold free-tier worker can take a minute to wake before it even starts.
SETTLE_TIMEOUT_SECONDS = 240
TERMINAL = {"confirmed", "failed"}


@dataclass
class LiveSend:
    sender: str
    remittance_id: str | None
    token_amount: str | None
    status: str
    xrpl_tx_hash: str | None
    detail: str = ""


def _candidates(ctx: RunContext) -> list[SeededPerson]:
    return [
        person
        for person in ctx.people.values()
        if person.persona.role == "sender"
        and person.verified
        and person.beneficiaries
        and person.clerk_user_id
        and person.clerk_user_id.startswith("user_")
    ]


def _ensure_balance(person: SeededPerson, amount: Decimal) -> None:
    from remitx_api.extensions import db
    from remitx_api.models.orm.account import CURRENCY_ZAR
    from remitx_api.repositories.account_repository import AccountRepository
    from remitx_api.services import deposit_service

    token = db.open_session()
    try:
        accounts = AccountRepository()
        zar = accounts.get_user_account(person.user_id, CURRENCY_ZAR)
        if accounts.get_available_balance(zar.account_id) >= amount:
            return
        deposit_service.process_deposits(
            [
                {
                    "date": datetime.now(UTC).isoformat(),
                    "reference": person.zar_reference,
                    "amount": str(amount + Decimal("100")),
                }
            ]
        )
    finally:
        db.close_session(token)


def make_live_tail(
    api_url: str,
    origin: str,
    *,
    transport: httpx.BaseTransport | None = None,
    poll_seconds: float = POLL_SECONDS,
):
    """The callable `engine.run_seed` runs after the replay. `transport` and
    `poll_seconds` exist for tests."""

    def live_tail(ctx: RunContext) -> dict:
        budget = Decimal(str(ctx.scenario.live_token_budget))
        spent = Decimal("0")
        results: list[LiveSend] = []
        candidates = _candidates(ctx)
        ctx.rng.shuffle(candidates)
        if not candidates:
            ctx.log(
                "Live tail skipped: no verified sender with a Clerk account and a "
                "beneficiary.",
                level="warning",
            )
        with httpx.Client(
            base_url=api_url.rstrip("/"), timeout=60, transport=transport
        ) as client:
            for person in candidates[: ctx.scenario.live_settlements]:
                result = _one(ctx, client, origin, person, budget - spent, poll_seconds)
                results.append(result)
                if result.remittance_id and result.token_amount:
                    spent += Decimal(result.token_amount)
                if result.status == "over_budget":
                    break
        ctx.log(f"Live tail: {len(results)} attempted, {spent} uctusd burned for real.")
        return {
            "budget": str(budget),
            "spent": str(spent),
            "sends": [asdict(r) for r in results],
        }

    return live_tail


def _one(
    ctx: RunContext,
    client: httpx.Client,
    origin: str,
    person: SeededPerson,
    budget_left: Decimal,
    poll_seconds: float,
) -> LiveSend:
    label = person.email or person.key
    try:
        _ensure_balance(person, SEND_ZAR)
        token = ctx.clerk.session_token(person.clerk_user_id)
        headers = {"Authorization": f"Bearer {token}", "Origin": origin}
        beneficiary = person.beneficiaries[0]
        quote = client.post(
            "/quotes",
            headers=headers,
            json={
                "beneficiary_id": str(beneficiary["beneficiary_id"]),
                "sender_amount": str(SEND_ZAR),
                "sender_currency": "ZAR",
                "receiver_payout_currency": beneficiary["currency"],
            },
        )
        quote.raise_for_status()
        quote_body = quote.json()
        token_amount = Decimal(str(quote_body["token_amount"]))
        if token_amount > budget_left:
            return LiveSend(
                label,
                None,
                str(token_amount),
                "over_budget",
                None,
                "would take the run past its "
                f"{ctx.scenario.live_token_budget} uctusd budget",
            )
        remittance = client.post(
            "/remittances", headers=headers, json={"quote_id": quote_body["quote_id"]}
        )
        remittance.raise_for_status()
        remittance_id = remittance.json()["remittance_id"]
        ctx.log(f"Live tail: {label} sent R{SEND_ZAR}; waiting for the real worker…")
        deadline = time.monotonic() + SETTLE_TIMEOUT_SECONDS
        status, tx_hash = "pending", None
        while time.monotonic() < deadline:
            time.sleep(poll_seconds)
            # Session tokens are short-lived; mint a fresh one per poll.
            headers["Authorization"] = (
                f"Bearer {ctx.clerk.session_token(person.clerk_user_id)}"
            )
            transfer = client.get(f"/remittances/{remittance_id}", headers=headers)
            transfer.raise_for_status()
            body = transfer.json()
            status, tx_hash = body["status"], body.get("xrpl_tx_hash")
            if status in TERMINAL:
                break
        ctx.count(f"live_tail.{status}")
        return LiveSend(label, remittance_id, str(token_amount), status, tx_hash)
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:200]
        if exc.response.status_code == 401:
            detail += (
                " (the API rejected the Clerk session token: check SEEDER_API_ORIGIN "
                "is one of the API's CORS_ORIGINS)"
            )
        return LiveSend(
            label,
            None,
            None,
            "not_sent",
            None,
            f"HTTP {exc.response.status_code}: {detail}",
        )
    except Exception as exc:  # noqa: BLE001 — reported per send
        return LiveSend(
            label, None, None, "not_sent", None, f"{type(exc).__name__}: {exc}"
        )
