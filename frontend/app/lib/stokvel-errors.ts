/**
 * The stokvel API's refusals and what to show for each (R4-08, #257; first
 * used by the contribute flow in #254). Codes and wording come from
 * docs/stokvel_integration.md §6, so the table there is the source of truth.
 */

import { errorMessage } from "~/hooks/use-onboarding"

export const STOKVEL_ERROR_MESSAGES = {
  contribution_already_paid: "You've already paid for this round.",
  not_a_member: "You're not a member of this stokvel's current cycle.",
  wrong_round: "This round isn't open for contributions.",
  contribution_amount_mismatch: "Something went wrong. Please try again.",
  round_not_finalisable: "This round can't be paid out yet.",
  round_already_finalised: "This round has already been paid out.",
  cycle_not_open: "This stokvel has no active cycle right now.",
  too_many_members: "This stokvel already has as many members as it can.",
  stokvel_paused: "Stokvels are temporarily paused.",
  treasury_allowance_missing: "Something went wrong. Please try again.",
  treasury_funds_low:
    "Contributions are temporarily unavailable. Please try again later.",
  // #232: a cycle has started but is not on-chain yet; worth a retry.
  cycle_starting:
    "This stokvel's cycle is still being set up. Try again in a minute.",
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

/** The §6 code on a failed call: the API sends `{ detail, code }`, with
 * `code` only on refusals that have one (`ErrorResponse`, #340). */
export function stokvelErrorCode(error: unknown): StokvelErrorCode | null {
  if (!(error instanceof Error) || !("body" in error)) return null
  const body = error.body
  if (!body || typeof body !== "object") return null
  const code = (body as { code?: unknown }).code
  return isStokvelErrorCode(code) ? code : null
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
    // "Your available ZAR balance is …" from the API; the mock says the same.
    if (/available \w* ?balance/i.test(error.message)) {
      return "insufficient_balance"
    }
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
