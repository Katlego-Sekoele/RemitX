/**
 * Admin manual release of a stokvel round (R4-11, #260; wired R4-09).
 */

import { queryOptions, type QueryClient } from "@tanstack/react-query"

import { sdk, type AdminStokvelRoundRead } from "~/client"

export type { AdminStokvelRoundRead }

export const FINALISE_REFUSALS = {
  round_not_finalisable: "This round can't be paid out yet.",
  round_already_finalised: "This round has already been paid out.",
  round_release_not_pending:
    "This round's payout is already in progress or has failed, so it can't be queued again.",
  stokvel_chain_mismatch:
    "This stokvel's records don't match the contract. An operator needs to check the vault before this round can be paid out.",
  stokvel_paused: "Stokvels are temporarily paused.",
} as const

export type FinaliseRefusalCode = keyof typeof FINALISE_REFUSALS

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

export function finaliseHint(
  round: Pick<
    AdminStokvelRoundRead,
    "paid_count" | "member_count" | "payout_time" | "release_status"
  >,
  now: Date = new Date()
): string | null {
  if (round.release_status === "released") return "Already paid out."
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
      queryFn: async ({ signal }) => {
        const { data } = await sdk.admin.stokvels.listAdminStokvelRounds({
          signal,
          throwOnError: true,
        })
        return data
      },
    }),
}

export const stokvelAdminMutations = {
  finalise: () => ({
    mutationFn: async (round: { stokvel_id: string; round: number }) => {
      const { data } = await sdk.admin.stokvels.finaliseStokvelRound({
        path: {
          stokvel_id: round.stokvel_id,
          round: round.round,
        },
        throwOnError: true,
      })
      return data
    },
  }),
}

export function invalidateAdminRounds(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: ROUNDS_KEY })
}
