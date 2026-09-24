"""RemitX's own ledger accounts — what the platform-accounts migration inserts
and what tests load.

One bank account and one fee revenue account per country RemitX settles fiat
in, each in that country's currency (a ZAR fee can no more land in a USD
revenue account than a ZAR deposit could land in the USD bank account), plus
the XRPL treasury wallet and the uctusd issuer it is funded from and burns
back to. None of them belongs to a user: `accounts.user_id` is set on `USER`
rows only.

The services find these rows by label (`deposit_service`,
`remittance_service`) or by (type, currency) (`AccountRepository
.get_platform_account`), so a label here is a lookup key, not a display
string. Opening a country is a new migration inserting its two rows, never an
edit to this tuple alone.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from remitx_api.config import Config
from remitx_api.models.orm.account import (
    CURRENCY_NAD,
    CURRENCY_TOKEN,
    CURRENCY_USD,
    CURRENCY_ZAR,
    CURRENCY_ZWL,
    TYPE_EXTERNAL,
    TYPE_PLATFORM_FIAT,
    TYPE_PLATFORM_REVENUE,
    TYPE_XRPL_WALLET,
)

# Fixed namespace for uuid5, so a seeded account has the same id in every
# environment and a migration can remove exactly the rows it inserted.
PLATFORM_ACCOUNT_NAMESPACE = uuid.UUID("5651721a-81c4-4806-84f9-e4294e7dc411")

TREASURY_WALLET_LABEL = "RemitX XRPL Treasury Wallet"
# The issuing address (ECO5040W clarifications): source of the treasury
# wallet's one-time pre-funding, destination of every withdrawal burn. Read
# from config, the same as `remittance_service.TOKEN_ISSUER_LABEL`, so the
# seeded label and the lookup cannot drift apart.
ISSUER_LABEL = Config().UCTUSD_ISSUER_LABEL


@dataclass(frozen=True, slots=True)
class PlatformAccountSeed:
    # Stable across label and config changes: what the account id derives from.
    key: str
    label: str
    type: str
    currency: str

    @property
    def account_id(self) -> uuid.UUID:
        return uuid.uuid5(PLATFORM_ACCOUNT_NAMESPACE, f"platform_account:{self.key}")


# (key prefix, label prefix, currency) per country RemitX settles fiat in.
_COUNTRIES = (
    ("sa", "RemitX SA", CURRENCY_ZAR),
    ("us", "RemitX US", CURRENCY_USD),
    ("zim", "RemitX ZIM", CURRENCY_ZWL),
    ("nam", "RemitX NAM", CURRENCY_NAD),
)

PLATFORM_ACCOUNT_SEEDS: tuple[PlatformAccountSeed, ...] = (
    *(
        PlatformAccountSeed(
            f"{key}_bank", f"{label} Bank Account", TYPE_PLATFORM_FIAT, currency
        )
        for key, label, currency in _COUNTRIES
    ),
    PlatformAccountSeed(
        "treasury_wallet", TREASURY_WALLET_LABEL, TYPE_XRPL_WALLET, CURRENCY_TOKEN
    ),
    *(
        PlatformAccountSeed(
            f"{key}_fee_revenue",
            f"{label} Fee Revenue",
            TYPE_PLATFORM_REVENUE,
            currency,
        )
        for key, label, currency in _COUNTRIES
    ),
    PlatformAccountSeed("uctusd_issuer", ISSUER_LABEL, TYPE_EXTERNAL, CURRENCY_TOKEN),
)
