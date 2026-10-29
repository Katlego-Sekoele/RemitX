"""rename the XRPL treasury wallet to the EVM treasury wallet

Ticket R3-02 (#239): the system moves from the XRP Ledger to the XRPL EVM
chain (D1). The treasury wallet's account type ``REMITX_XRPL_WALLET`` becomes
``REMITX_EVM_WALLET`` and its label "RemitX XRPL Treasury Wallet" becomes
"RemitX Treasury Wallet", matching ``platform_account_seed.py``.

These are values, not columns, so there is no expand step that both
releases can read. While the rollout runs, an API instance on the previous
release cannot find the treasury by its old label: a remittance confirmed in
that window fails before anything is committed, its quote stays active, and
the customer can confirm it again. The worker does not look the treasury up
by label or type, so settlement is unaffected.

Revision ID: 879fc80b8041
Revises: 45ec46232228
Create Date: 2026-10-11 10:04:00.000000+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "879fc80b8041"
down_revision: str | None = "45ec46232228"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_OLD_TYPE, _NEW_TYPE = "REMITX_XRPL_WALLET", "REMITX_EVM_WALLET"
_OLD_LABEL, _NEW_LABEL = "RemitX XRPL Treasury Wallet", "RemitX Treasury Wallet"


def _type_check(wallet_type: str) -> str:
    return (
        f"type IN ('USER','REMITX_FIAT','{wallet_type}',"
        "'REMITX_REVENUE','EXTERNAL','STOKVEL')"
    )


def _rename(old_type: str, new_type: str, old_label: str, new_label: str) -> None:
    op.drop_constraint("accounts_type_valid", "accounts", type_="check")
    op.execute(f"UPDATE accounts SET type = '{new_type}' WHERE type = '{old_type}'")
    op.execute(
        f"UPDATE accounts SET label = '{new_label}'"
        f" WHERE label = '{old_label}' AND type <> 'USER'"
    )
    op.create_check_constraint("accounts_type_valid", "accounts", _type_check(new_type))


def upgrade() -> None:
    _rename(_OLD_TYPE, _NEW_TYPE, _OLD_LABEL, _NEW_LABEL)


def downgrade() -> None:
    _rename(_NEW_TYPE, _OLD_TYPE, _NEW_LABEL, _OLD_LABEL)
