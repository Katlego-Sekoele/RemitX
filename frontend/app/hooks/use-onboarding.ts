import {
  useMutation,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query"
import { useNavigate, useOutletContext } from "react-router"

import {
  api,
  sdk,
  type KycApplicationPatch,
  type KycApplicationDetailRead as KycApplicationDetail,
} from "~/client"
import { applicationStepPath } from "~/lib/kyc-onboarding"

/** The application the wizard is editing, loaded by `steps-layout.tsx`. */
export function useOnboarding() {
  return useOutletContext<KycApplicationDetail>()
}

export function nextPathAfter(
  detail: KycApplicationDetail,
  current: string
): string {
  const index = detail.steps.findIndex((step) => step.step === current)
  const following = detail.steps[index + 1]
  return applicationStepPath(
    detail.application.application_id,
    following?.step ?? detail.next_step
  )
}

/** Put a fresh detail in the cache, and mark the standing and history stale —
 * a save or submit can change either. */
export function storeApplication(
  queryClient: QueryClient,
  detail: KycApplicationDetail
) {
  queryClient.setQueryData(
    api.kyc.onboarding.getMyApplication({
      path: { application_id: detail.application.application_id },
    }).queryKey,
    detail
  )
  queryClient.invalidateQueries({
    queryKey: api.kyc.onboarding.getApplication().queryKey,
  })
  queryClient.invalidateQueries({
    queryKey: api.kyc.onboarding.listMyApplications().queryKey,
  })
}

export function useSaveStep(current: string) {
  const { application } = useOnboarding()
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  return useMutation({
    mutationFn: async (
      fields: Omit<KycApplicationPatch, "expected_version">
    ) => {
      const { data } = await sdk.kyc.onboarding.patchApplication({
        path: { application_id: application.application_id },
        body: { expected_version: application.version, ...fields },
        throwOnError: true,
      })
      return data
    },
    onSuccess: (data) => {
      storeApplication(queryClient, data)
      navigate(nextPathAfter(data, current))
    },
  })
}

export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong."
}
