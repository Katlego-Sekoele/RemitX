/**
 * The stokvel API's refusals and what to show for each (R4-08, #257; first
 * used by the contribute flow in #254). Codes and wording come from
 * docs/stokvel_integration.md §6, so the table there is the source of truth.
 */

import { errorMessage } from "~/hooks/use-onboarding"
import { MAX_STOKVEL_MEMBERS } from "~/lib/stokvel-create"

export const STOKVEL_ERROR_MESSAGES = {
  contribution_already_paid: "You've already paid for this round.",
  not_a_member: "You're not a member of this stokvel's current cycle.",
  wrong_round: "This round isn't open for contributions.",
  contribution_amount_mismatch: "Something went wrong. Please try again.",
  round_not_finalisable: "This round can't be paid out yet.",
  round_already_finalised: "This round has already been paid out.",
  cycle_not_open: "This stokvel has no active cycle right now.",
  too_many_members: `A stokvel can have at most ${MAX_STOKVEL_MEMBERS} members.`,
  stokvel_paused: "Stokvels are temporarily paused.",
  treasury_allowance_missing: "Something went wrong. Please try again.",
  treasury_funds_low:
    "Contributions are temporarily unavailable. Please try again later.",
} as const

export type StokvelErrorCode = keyof typeof STOKVEL_ERROR_MESSAGES

export function isStokvelErrorCode(value: unknown): value is StokvelErrorCode {
  return typeof value === "string" && value in STOKVEL_ERROR_MESSAGES
}

function statusOf(error: unknown): number | null {
  return error instanceof Error &&
    "status" in error &&
    typeof error.status === "number"
    ? error.status
    : null
}

/**
 * The §6 code on a failed call, if it carries one. The API puts it in the
 * body as `{code}` or `{detail: {code}}`; until #233 lands, the message is
 * also searched so a mock or a bare `{detail: "stokvel_paused"}` still maps.
 */
export function stokvelErrorCode(error: unknown): StokvelErrorCode | null {
  if (!(error instanceof Error)) return null
  const body = "body" in error ? error.body : undefined
  if (body && typeof body === "object") {
    const direct = (body as { code?: unknown }).code
    if (isStokvelErrorCode(direct)) return direct
    const detail = (body as { detail?: unknown }).detail
    if (isStokvelErrorCode(detail)) return detail
    if (detail && typeof detail === "object") {
      const nested = (detail as { code?: unknown }).code
      if (isStokvelErrorCode(nested)) return nested
    }
  }
  const match = error.message.match(/\b[a-z]+(?:_[a-z]+)+\b/g)
  return match?.find(isStokvelErrorCode) ?? null
}

/** The §6 wording for a known code, otherwise the API's own message. */
export function stokvelErrorMessage(error: unknown): string {
  const code = stokvelErrorCode(error)
  return code ? STOKVEL_ERROR_MESSAGES[code] : errorMessage(error)
}

/** Why a contribution was refused, including the ledger's own refusals that
 * `POST /stokvels/{id}/contributions` shares with `POST /remittances`. */
export type ContributeRefusal =
  | StokvelErrorCode
  | "insufficient_balance"
  | "over_limit"
  | "unverified"
  | "other"

export function contributeRefusal(error: unknown): ContributeRefusal {
  const code = stokvelErrorCode(error)
  if (code) return code
  const status = statusOf(error)
  if (status === 403) return "unverified"
  if (status === 400 && error instanceof Error) {
    if (/available balance/i.test(error.message)) return "insufficient_balance"
    if (/\b(daily|monthly) limit\b/i.test(error.message)) return "over_limit"
  }
  return "other"
}

export function contributeRefusalMessage(
  refusal: ContributeRefusal,
  error: unknown
): string {
  switch (refusal) {
    case "insufficient_balance":
      return "Your balance is too low for this round. Top up first; deposits take time to confirm."
    case "over_limit":
      return "This contribution would take you over your sending limit. Contributions count toward your limits."
    case "unverified":
      return "Only verified members can contribute."
    case "other":
      return errorMessage(error)
    default:
      return STOKVEL_ERROR_MESSAGES[refusal]
  }
}

/** Refusals that are not worth a retry button. */
export function isFinalRefusal(refusal: ContributeRefusal): boolean {
  return (
    refusal === "contribution_already_paid" ||
    refusal === "not_a_member" ||
    refusal === "cycle_not_open" ||
    refusal === "unverified"
  )
}
