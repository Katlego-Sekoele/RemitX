"""Baseline KYC reference data for migrations and tests.

Reason codes and status progressions are seeded from the Python enums so the
database and application agree on the closed sets they enforce.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from remitx_api.models.orm.kyc_lifecycle import (
    APPLICATION_STATUSES,
    KYC_APPLICATION_STATUS_DESCRIPTIONS,
    KYC_REASON_CODE_DESCRIPTIONS,
    LEGAL_TRANSITIONS,
    OPEN_STATUSES,
    KycReasonCode,
    KycStatus,
)

KYC_NAMESPACE = uuid.UUID("8f14e45f-ceea-467a-9a5f-0d2a5c8b4e01")


def precompute_progression_id(from_status: str, to_status: str) -> uuid.UUID:
    return uuid.uuid5(KYC_NAMESPACE, f"progression:{from_status}:{to_status}")


@dataclass(frozen=True, slots=True)
class KycReasonCodeSeed:
    code: KycReasonCode
    description: str


REASON_CODE_SEEDS: tuple[KycReasonCodeSeed, ...] = tuple(
    KycReasonCodeSeed(code, description)
    for code, description in KYC_REASON_CODE_DESCRIPTIONS.items()
)


@dataclass(frozen=True, slots=True)
class KycStatusProgressionSeed:
    from_status: KycStatus
    to_status: KycStatus


PROGRESSION_SEEDS: tuple[KycStatusProgressionSeed, ...] = tuple(
    KycStatusProgressionSeed(from_status, to_status)
    for from_status, targets in LEGAL_TRANSITIONS.items()
    for to_status in sorted(targets, key=lambda status: status.value)
)


@dataclass(frozen=True, slots=True)
class KycApplicationStatusSeed:
    status: KycStatus
    description: str
    is_open: bool
    is_terminal: bool


APPLICATION_STATUS_SEEDS: tuple[KycApplicationStatusSeed, ...] = tuple(
    KycApplicationStatusSeed(
        status=KycStatus(status),
        description=KYC_APPLICATION_STATUS_DESCRIPTIONS[KycStatus(status)],
        is_open=KycStatus(status) in OPEN_STATUSES,
        is_terminal=len(LEGAL_TRANSITIONS[KycStatus(status)]) == 0,
    )
    for status in APPLICATION_STATUSES
)

if {seed.code for seed in REASON_CODE_SEEDS} != set(KycReasonCode):
    raise RuntimeError("REASON_CODE_SEEDS must cover every KycReasonCode member")

if {seed.status.value for seed in APPLICATION_STATUS_SEEDS} != set(
    APPLICATION_STATUSES
):
    raise RuntimeError("APPLICATION_STATUS_SEEDS must cover every application status")
