import { useQuery, useSuspenseQuery } from "@tanstack/react-query"

import { KYC_REFERENCE_KEY } from "~/lib/kyc-reference"
import { useApi } from "~/lib/use-api"

/** Countries and identity schemes change only with a migration. */
const REFERENCE_STALE_TIME = Number.POSITIVE_INFINITY

export function useKycReferenceQuery() {
  const api = useApi()
  return useQuery({
    queryKey: KYC_REFERENCE_KEY,
    queryFn: api.getKycReference,
    staleTime: REFERENCE_STALE_TIME,
  })
}

/**
 * For the onboarding steps. The onboarding layout loads the reference data
 * before rendering a step, so this reads the cache and never suspends there.
 */
export function useKycReference() {
  const api = useApi()
  return useSuspenseQuery({
    queryKey: KYC_REFERENCE_KEY,
    queryFn: api.getKycReference,
    staleTime: REFERENCE_STALE_TIME,
  }).data
}
