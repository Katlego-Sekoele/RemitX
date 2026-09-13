import { useQuery, useSuspenseQuery } from "@tanstack/react-query"
import { api } from "~/client"

/** Countries and identity schemes change only with a migration. */
const REFERENCE_STALE_TIME = Number.POSITIVE_INFINITY

export function useKycReferenceQuery() {
  return useQuery({
    ...api.kyc.onboarding.getReference(),
    staleTime: REFERENCE_STALE_TIME,
  })
}

/**
 * For the onboarding steps. The onboarding layout loads the reference data
 * before rendering a step, so this reads the cache and never suspends there.
 */
export function useKycReference() {
  return useSuspenseQuery({
    ...api.kyc.onboarding.getReference(),
    staleTime: REFERENCE_STALE_TIME,
  }).data
}
