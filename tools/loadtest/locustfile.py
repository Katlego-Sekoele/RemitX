"""Load test for the RemitX API: seeded people doing what the web app does.

Run it with `make loadtest` (run.sh), which prepares everything this file
reads. Senders open the pages the app opens, price transfers, send money and
then poll the transfer until it settles, as the transfer page does. Staff
browse the admin queues.

Nothing here talks to Clerk: every session token is signed with the throwaway
key prepare.py generated, whose public half the API verifies with
(CLERK_JWT_KEY).

Settlement gets its own rows in the report (type SETTLE), timed with the API's
own timestamps rather than by polling:
- "queue wait": sent until the worker picked the burn up
- "chain + confirm": picked up until settled (the burn and the confirm task)
- "end to end": sent until settled; its rate is the queue's throughput
"""

import itertools
import json
import os
import random
import time
from datetime import datetime
from pathlib import Path

import jwt
from locust import HttpUser, LoadTestShape, between, events, task

RUN_DATA = Path(os.environ.get("LOADTEST_RUN_DATA", "/run-data"))
PEOPLE = json.loads((RUN_DATA / "people.json").read_text())
SIGNING_KEY = (RUN_DATA / "jwt_private.pem").read_text()

# How often the transfer page polls (VITE_TRANSFER_POLL_INTERVAL_MS).
POLL_SECONDS = 3
# A transfer not settled by then is recorded as a failed settlement.
SETTLE_TIMEOUT_SECONDS = 600
TOKEN_LIFETIME_SECONDS = 24 * 60 * 60
SEND_AMOUNTS_ZAR = ("100", "150", "200", "250", "300", "400", "500")
IN_FLIGHT = ("pending", "processing")

# What each admin read permission lets a staff member open.
ADMIN_PAGES = {
    "transaction:read_any": ["/admin/operations"],
    "kyc:application:read": ["/admin/kyc/queue-count", "/admin/kyc/applications"],
    "cashin:read": ["/admin/deposits/pending-count", "/admin/deposits/pending"],
}


def _in_turn(people: list[dict]):
    """Hand people out one at a time, so concurrent users are different
    people: two users sharing a sender would queue on one account's lock."""
    shuffled = random.sample(people, len(people))
    return itertools.cycle(shuffled)


def session_token(person: dict) -> str:
    now = int(time.time())
    claims = {
        "sub": person["clerk_user_id"],
        "azp": PEOPLE["origin"],
        "iat": now,
        "nbf": now,
        "exp": now + TOKEN_LIFETIME_SECONDS,
        # Carried so a first request never needs Clerk to look them up.
        "email": person["email"],
        "first_name": person["first_name"],
    }
    return jwt.encode(claims, SIGNING_KEY, algorithm="RS256")


def _milliseconds(start: str, end: str) -> float:
    elapsed = datetime.fromisoformat(end) - datetime.fromisoformat(start)
    return elapsed.total_seconds() * 1000


def _record_settlement(name: str, milliseconds: float, error=None) -> None:
    events.request.fire(
        request_type="SETTLE",
        name=name,
        response_time=milliseconds,
        response_length=0,
        response=None,
        context={},
        exception=error,
    )


class Person(HttpUser):
    abstract = True
    people = None

    def on_start(self) -> None:
        self.person = next(self.people)
        self.client.headers["Authorization"] = f"Bearer {session_token(self.person)}"


class Sender(Person):
    weight = 19
    wait_time = between(1, 5)
    people = _in_turn(PEOPLE["senders"])

    @task(3)
    def open_home(self) -> None:
        self.client.get("/kyc/application")
        self.client.get("/accounts")

    @task(2)
    def open_send_form(self) -> None:
        self.client.get("/accounts")
        self.client.get("/beneficiaries/get-beneficiary-list")
        self.client.post("/quotes/preview-quote", json=self._pricing(self._payee()))

    @task(2)
    def open_transfers(self) -> None:
        self.client.get("/remittances")

    @task(1)
    def send_money(self) -> None:
        payee = self._payee()
        quote = self.client.post(
            "/quotes/create-quote",
            json={"beneficiary_id": payee["beneficiary_id"], **self._pricing(payee)},
        )
        if not quote.ok:
            return
        sent = self.client.post(
            "/remittances", json={"quote_id": quote.json()["quote_id"]}
        )
        if not sent.ok:
            return
        self._follow(sent.json()["remittance_id"])

    def _payee(self) -> dict:
        return random.choice(self.person["beneficiaries"])

    def _pricing(self, payee: dict) -> dict:
        return {
            "sender_amount": random.choice(SEND_AMOUNTS_ZAR),
            "sender_currency": "ZAR",
            "receiver_payout_currency": payee["payout_currency"],
        }

    def _follow(self, remittance_id: str) -> None:
        """Poll the transfer like the transfer page, then record how long
        settling took from the API's own timestamps."""
        started = time.monotonic()
        while True:
            response = self.client.get(
                f"/remittances/{remittance_id}", name="/remittances/[id]"
            )
            if not response.ok:
                return
            transfer = response.json()
            if transfer["status"] not in IN_FLIGHT:
                break
            if time.monotonic() - started > SETTLE_TIMEOUT_SECONDS:
                _record_settlement(
                    "end to end",
                    SETTLE_TIMEOUT_SECONDS * 1000,
                    TimeoutError(f"not settled after {SETTLE_TIMEOUT_SECONDS}s"),
                )
                return
            time.sleep(POLL_SECONDS)

        if transfer["status"] != "confirmed":
            _record_settlement(
                "end to end",
                (time.monotonic() - started) * 1000,
                RuntimeError(f"settlement {transfer['status']}"),
            )
            return
        created, picked_up, settled = (
            transfer["created_at"],
            transfer["processed_at"],
            transfer["settled_at"],
        )
        _record_settlement("queue wait", _milliseconds(created, picked_up))
        _record_settlement("chain + confirm", _milliseconds(picked_up, settled))
        _record_settlement("end to end", _milliseconds(created, settled))


if PEOPLE["staff"]:

    class Staff(Person):
        weight = 1
        wait_time = between(2, 8)
        people = _in_turn(PEOPLE["staff"])

        def on_start(self) -> None:
            super().on_start()
            self.pages = [
                page
                for permission in self.person["permissions"]
                for page in ADMIN_PAGES[permission]
            ]

        @task
        def open_admin_page(self) -> None:
            self.client.get(random.choice(self.pages))


class SteppedLoad(LoadTestShape):
    """Hold each user count for a while, then step up. Where response times
    bend and errors start is the number to report.

    run.sh loads these from the profile (LOADTEST_STEPS, LOADTEST_STEP_SECONDS,
    LOADTEST_SPAWN_RATE). Edit tools/loadtest/profiles/*.json to change them.
    """

    # `or`, not a get() default: compose passes an unset knob through as "".
    steps = [
        int(n)
        for n in (os.environ.get("LOADTEST_STEPS") or "10,25,50,100,200").split(",")
    ]
    step_seconds = int(os.environ.get("LOADTEST_STEP_SECONDS") or "120")
    spawn_rate = float(os.environ.get("LOADTEST_SPAWN_RATE") or "10")

    def tick(self):
        step = int(self.get_run_time() // self.step_seconds)
        if step >= len(self.steps):
            return None
        return self.steps[step], self.spawn_rate
