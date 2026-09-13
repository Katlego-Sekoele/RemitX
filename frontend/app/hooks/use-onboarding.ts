import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useOutletContext } from "react-router"

import type { KycOnboarding } from "~/lib/api"
import { KYC_ONBOARDING_KEY, pathForStep } from "~/lib/kyc-onboarding"
import { useApi } from "~/lib/use-api"

export function useOnboarding() {
  return useOutletContext<KycOnboarding>()
}

export function nextPathAfter(
  onboarding: KycOnboarding,
  current: string
): string {
  const index = onboarding.steps.findIndex((step) => step.step === current)
  const following = onboarding.steps[index + 1]
  return pathForStep(following?.step ?? onboarding.next_step)
}

export function useSaveStep(current: string) {
  const api = useApi()
  const onboarding = useOnboarding()
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  return useMutation({
    mutationFn: async (fields: Record<string, unknown>) => {
      let version = onboarding.application?.version
      if (version === undefined) {
        const started = await api.startKycOnboarding()
        version = started.application?.version
        if (version === undefined) {
          throw new Error("Could not start an application.")
        }
      }
      return api.patchKycOnboarding({
        expected_version: version,
        ...fields,
      })
    },
    onSuccess: (data) => {
      queryClient.setQueryData(KYC_ONBOARDING_KEY, data)
      navigate(nextPathAfter(data, current))
    },
  })
}

export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong."
}
