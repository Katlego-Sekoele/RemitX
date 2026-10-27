/**
 * Admin emergency stop for every stokvel (R4-07, #256; wired R4-09).
 */

import { queryOptions, type QueryClient } from "@tanstack/react-query"

import {
  sdk,
  type StokvelContractPauseRequest,
  type StokvelContractRead,
} from "~/client"

export type { StokvelContractPauseRequest, StokvelContractRead }

export const PAUSE_REASON_MIN = 10
export const PAUSE_REASON_MAX = 500

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
      queryFn: async ({ signal }) => {
        const { data } = await sdk.admin.stokvel_contract.getStokvelContract({
          signal,
          throwOnError: true,
        })
        return data
      },
    }),
}

export const stokvelContractMutations = {
  pause: () => ({
    mutationFn: async (body: StokvelContractPauseRequest) => {
      const { data } = await sdk.admin.stokvel_contract.pauseStokvelContract({
        body,
        throwOnError: true,
      })
      return data
    },
  }),
  resume: () => ({
    mutationFn: async () => {
      const { data } = await sdk.admin.stokvel_contract.unpauseStokvelContract({
        throwOnError: true,
      })
      return data
    },
  }),
}

export function invalidateStokvelContract(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: CONTRACT_KEY })
}
