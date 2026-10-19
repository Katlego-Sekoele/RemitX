/**
 * The admin's manual release of a stokvel round (R4-11, #260), the fallback
 * when the automatic release fails (D5, P5: approved by product, 19 Oct).
 * The route is R3-10 (#247), not built yet:
 * `POST /admin/stokvels/{id}/rounds/{n}/finalise`, which asks the contract to
 * release the round and writes `stokvel.round.finalised_manually` to the
 * audit log. No admin route lists stokvels and their rounds yet either, so
 * the page reads `stokvel-admin.mock.ts` for both; R4-09 swaps them for the
 * generated client and deletes the mock.
 */

import { queryOptions, type QueryClient } from "@tanstack/react-query"

import {
  finaliseRoundMock,
  listAdminRoundsMock,
} from "~/lib/stokvel-admin.mock"

/** One round as the admin page lists it. R4-09: replace with `~/client`
 * once #247 (or its list route) is built; the shape is assumed. */
export type AdminStokvelRoundRead = {
  stokvel_id: string
  stokvel_name: string
  /** 0-based, like the contract. */
  round: number
  total_rounds: number
  recipient_name: string
  paid_count: number
  member_count: number
  payout_time: string
  release_status: "pending" | "processing" | "released" | "failed" | null
  release_tx_hash: string | null
}

/** Doc §6 codes the finalise route answers with, and what the admin sees. */
export const FINALISE_REFUSALS = {
  round_not_finalisable: "This round can't be paid out yet.",
  round_already_finalised: "This round has already been paid out.",
  stokvel_paused: "Stokvels are temporarily paused.",
} as const

export type FinaliseRefusalCode = keyof typeof FINALISE_REFUSALS

/** The admin-facing message for a failed finalise: the §6 wording for a
 * known `code`, otherwise the API's own `detail`. */
export function finaliseRefusalMessage(error: unknown): string {
  if (error instanceof Error && "body" in error) {
    const body = error.body
    if (body && typeof body === "object") {
      const code = (body as { code?: unknown }).code
      if (typeof code === "string" && code in FINALISE_REFUSALS) {
        return FINALISE_REFUSALS[code as FinaliseRefusalCode]
      }
    }
    return error.message
  }
  return "Something went wrong. Please try again."
}

/**
 * Why a round can't be released yet, or null when it looks ready: every
 * member has paid and its payout time has passed (D12). Only a hint: the
 * contract decides, and the button still lets the admin try, which is how
 * the demo shows an early release being refused.
 */
export function finaliseHint(
  round: Pick<
    AdminStokvelRoundRead,
    "paid_count" | "member_count" | "payout_time" | "release_status"
  >,
  now: Date = new Date()
): string | null {
  if (round.release_status === "released") return "Already paid out."
  // The worker's own release is in flight: a second one must not be sent.
  if (round.release_status === "processing") return "Release in progress."
  const waiting = round.member_count - round.paid_count
  if (waiting > 0) {
    return `Waiting for ${waiting} ${waiting === 1 ? "member" : "members"} to pay.`
  }
  if (Date.parse(round.payout_time) > now.getTime()) {
    return "Its payout time hasn't come yet."
  }
  return null
}

/**
 * Whether the page offers Release payout for a round: not once it has been
 * released, and not while the worker's release is in flight. A failed
 * release keeps the button: that's the case the fallback exists for (P5).
 */
export function canReleaseByHand(
  round: Pick<AdminStokvelRoundRead, "release_status">
): boolean {
  return (
    round.release_status !== "released" && round.release_status !== "processing"
  )
}

const ROUNDS_KEY = ["admin", "stokvel-rounds"] as const

export const stokvelAdminQueries = {
  rounds: () =>
    queryOptions({
      queryKey: ROUNDS_KEY,
      queryFn: () => listAdminRoundsMock(),
    }),
}

export const stokvelAdminMutations = {
  /** `POST /admin/stokvels/{id}/rounds/{n}/finalise` (#247, assumed). */
  finalise: () => ({
    mutationFn: (round: { stokvel_id: string; round: number }) =>
      finaliseRoundMock(round.stokvel_id, round.round),
  }),
}

export function invalidateAdminRounds(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: ROUNDS_KEY })
}
