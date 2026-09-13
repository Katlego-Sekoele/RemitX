import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useOutletContext } from "react-router"

import {
  api,
  sdk,
  type KycApplicationPatch,
  type KycOnboardingRead as KycOnboarding,
} from "~/client"
import { pathForStep } from "~/lib/kyc-onboarding"

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
  const onboarding = useOnboarding()
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  return useMutation({
    mutationFn: async (
      fields: Omit<KycApplicationPatch, "expected_version">
    ) => {
      let version = onboarding.application?.version
      if (version === undefined) {
        const { data: started } = await sdk.kyc.onboarding.startApplication({
          throwOnError: true,
        })
        version = started.application?.version
        if (version === undefined) {
          throw new Error("Could not start an application.")
        }
      }
      const { data } = await sdk.kyc.onboarding.patchApplication({
        body: { expected_version: version, ...fields },
        throwOnError: true,
      })
      return data
    },
    onSuccess: (data) => {
      queryClient.setQueryData(
        api.kyc.onboarding.getApplication().queryKey,
        data
      )
      navigate(nextPathAfter(data, current))
    },
  })
}

export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong."
}
