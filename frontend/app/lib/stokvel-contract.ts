/**
 * The admin's emergency stop for every stokvel (R4-07, #256).
 * `POST /admin/stokvel-contract/pause` and `/unpause` (#244) return only a
 * transaction hash. No route reads the address, paused flag or treasury
 * balance, so this page still reads and writes `stokvel-contract.mock.ts`.
 *
 * Pausing stops contributions and payouts on the contract; creating stokvels
 * and starting cycles keep working (doc §1, `pause()` / `unpause()`).
 */

import { queryOptions, type QueryClient } from "@tanstack/react-query"

import {
  getStokvelContractMock,
  pauseStokvelContractMock,
  resumeStokvelContractMock,
} from "~/lib/stokvel-contract.mock"

/** The contract as the admin page shows it. Assumed until a read route
 * exists. `paused_at` and `paused_reason` are not on the pause response. */
export type StokvelContractRead = {
  address: string
  network: string
  paused: boolean
  /** When the current pause began; null while running. */
  paused_at: string | null
  /** The reason given for the current pause; null while running. */
  paused_reason: string | null
  treasury_token_balance: string
}

/** `POST /admin/stokvel-contract/pause` (#244). The page still calls the mock. */
export type StokvelPauseRequest = {
  reason: string
}

export const PAUSE_REASON_MIN = 10
export const PAUSE_REASON_MAX = 500

/** Why a pause reason can't be sent yet, or null. The reason goes into the
 * audit log, so it should say enough for someone reading it later. */
export function pauseReasonIssue(reason: string): string | null {
  const trimmed = reason.trim()
  if (!trimmed) return "Give a reason. It's recorded in the audit log."
  if (trimmed.length < PAUSE_REASON_MIN) {
    return `Say a little more: at least ${PAUSE_REASON_MIN} characters.`
  }
  if (trimmed.length > PAUSE_REASON_MAX) {
    return `Keep it to ${PAUSE_REASON_MAX} characters.`
  }
  return null
}

const CONTRACT_KEY = ["admin", "stokvel-contract"] as const

export const stokvelContractQueries = {
  status: () =>
    queryOptions({
      queryKey: CONTRACT_KEY,
      queryFn: () => getStokvelContractMock(),
    }),
}

export const stokvelContractMutations = {
  pause: () => ({
    mutationFn: (body: StokvelPauseRequest) => pauseStokvelContractMock(body),
  }),
  resume: () => ({
    mutationFn: () => resumeStokvelContractMock(),
  }),
}

export function invalidateStokvelContract(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: CONTRACT_KEY })
}
