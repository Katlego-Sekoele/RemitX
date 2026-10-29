"""A stokvel's payout (D6) has a quote with no sender user, only
`quotes.stokvel_id` (R3-02). The transfer reads join the sender user, so
they must still list it: for the recipient, on their dashboard, and in the
staff overview's totals. The recipient sees the stokvel's name where a
sender's name would go."""

from decimal import Decimal

import pytest
from remitx_api.db.rls import bound_row_security_context
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_TOKEN, CURRENCY_ZAR
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.quote import Quote
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.transaction import STATUS_CONFIRMED, STATUS_PENDING
from remitx_api.repositories.stokvel_repository import StokvelRepository
from sqlalchemy import func, select
from tests.kyc_helpers import make_user
from tests.rbac_helpers import make_user as make_staff, rbac_client
from tests.send_helpers import record_transfer


def _record_payout(recipient, *, status: str = STATUS_PENDING):
    """A round's payout from a new stokvel to `recipient`. Flushed only."""
    stokvel = Stokvel(
        organiser_user_id=make_user().id,
        name="Savings club",
        currency=CURRENCY_ZAR,
        contribution_amount=Decimal("500"),
    )
    db.session.add(stokvel)
    db.session.flush()
    return record_transfer(
        stokvel,
        recipient,
        sender_amount=Decimal("1500"),
        token_amount=Decimal("75"),
        status=status,
    )


def _payout_to(recipient) -> str:
    token = db.open_session()
    try:
        remittance = _record_payout(recipient)
        db.session.commit()
        return str(remittance.remittance_id)
    finally:
        db.close_session(token)


def test_the_recipient_lists_a_stokvel_payout(verified_client):
    client, recipient = verified_client
    remittance_id = _payout_to(recipient)

    listed = client.get("/remittances")

    assert listed.status_code == 200
    [transfer] = listed.json()
    assert transfer["remittance_id"] == remittance_id
    assert transfer["direction"] == "received"
    assert transfer["counterparty_user_id"] is None
    assert transfer["counterparty_name"] == "Savings club"


def test_the_recipient_reads_a_stokvel_payout(verified_client):
    client, recipient = verified_client
    remittance_id = _payout_to(recipient)

    response = client.get(f"/remittances/{remittance_id}")

    assert response.status_code == 200
    assert response.json()["direction"] == "received"
    assert response.json()["counterparty_user_id"] is None
    assert response.json()["counterparty_name"] == "Savings club"


def test_a_stokvel_payout_is_in_the_recipients_account_history(verified_client):
    client, recipient = verified_client
    remittance_id = _payout_to(recipient)
    accounts = {a["currency"]: a for a in client.get("/accounts").json()}

    response = client.get(
        "/accounts-history",
        params={"account_id": accounts[CURRENCY_TOKEN]["account_id"]},
    )

    assert response.status_code == 200, response.text
    [leg] = response.json()
    assert leg["remittance_id"] == remittance_id
    assert leg["direction"] == "in"
    assert leg["amount"] == "75.00"
    assert leg["counterparty_name"] == "Savings club"
    assert leg["description"] == "Stokvel payout from Savings club"


def test_a_stokvel_payout_is_in_flight_on_the_recipients_dashboard(
    verified_client,
):
    client, recipient = verified_client
    remittance_id = _payout_to(recipient)

    body = client.get("/dashboard").json()

    assert body["has_transfers"] is True
    [in_flight] = body["in_flight"]
    assert in_flight["remittance_id"] == remittance_id
    assert in_flight["direction"] == "received"
    assert in_flight["counterparty_name"] == "Savings club"
    assert body["limits"]["daily_sent_zar"] == "0.00"


def test_a_stokvel_payout_counts_in_the_staff_overview():
    with rbac_client(
        make_staff("ops-stokvel-reader"),
        permissions=(PermissionCode.TRANSACTION_READ_ANY,),
    ) as client:
        _record_payout(make_user(), status=STATUS_CONFIRMED)
        db.session.commit()

        body = client.get("/admin/operations").json()

    assert sum(Decimal(day["token_settled"]) for day in body["volume"]) == Decimal("75")
    assert sum(day["settled"] for day in body["pipeline"]) == 1


@pytest.mark.postgres
def test_a_recipient_outside_the_stokvel_sees_only_its_name(postgres_app):
    """Row-level security hides the stokvel from a recipient who is not a
    member. `stokvel_payout_name` still gives them its name, and gives it to
    no one the stokvel has not paid."""
    token = db.open_session()
    try:
        recipient, outsider = make_user(), make_user()
        quote_id = _record_payout(recipient).quote_id
        db.session.commit()
        # By its quote, not its name: other tests' stokvels share the database.
        stokvel_id = db.session.scalar(
            select(Quote.stokvel_id).where(Quote.quote_id == quote_id)
        )

        with bound_row_security_context(recipient.id, is_admin_route=False):
            hidden = db.session.scalars(
                select(Stokvel.id).where(Stokvel.id == stokvel_id)
            ).all()
            names = StokvelRepository().get_stokvel_names({stokvel_id})
        with bound_row_security_context(outsider.id, is_admin_route=False):
            outsider_sees = db.session.scalar(
                select(func.stokvel_payout_name(stokvel_id))
            )

        assert hidden == []
        assert names == {stokvel_id: "Savings club"}
        assert outsider_sees is None
    finally:
        db.close_session(token)
