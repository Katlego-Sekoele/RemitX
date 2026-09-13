import { useQuery } from "@tanstack/react-query"
import { Outlet, useLocation } from "react-router"

import { AppPageFrame } from "~/components/app-dashboard/app-page-frame"
import { RejectionBanner } from "~/components/kyc/rejection-banner"
import { OnboardingProgress } from "~/components/kyc/onboarding-progress"
import { SelfDeclaredNotice } from "~/components/kyc/self-declared-notice"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { Skeleton } from "~/components/ui/skeleton"
import { useKycReferenceQuery } from "~/hooks/use-kyc-reference"
import { KYC_ONBOARDING_KEY } from "~/lib/kyc-onboarding"
import { useApi } from "~/lib/use-api"
import type { Route } from "./+types/layout"

export function meta(): Route.MetaDescriptors {
  return [
    { title: "Verification — RemitX" },
    { name: "robots", content: "noindex" },
  ]
}

function stepFromPath(pathname: string) {
  if (pathname === "/app/verification") return "welcome"
  return pathname.replace(/^\/app\/verification\//, "")
}

export default function OnboardingLayout() {
  const api = useApi()
  const { pathname } = useLocation()
  const current = stepFromPath(pathname)
  const query = useQuery({
    queryKey: KYC_ONBOARDING_KEY,
    queryFn: api.getKycOnboarding,
  })
  // Steps read countries and identity schemes synchronously, so both load
  // before any step renders.
  const reference = useKycReferenceQuery()
  const error = query.error ?? reference.error

  return (
    <AppPageFrame module="routes/onboarding/welcome.tsx">
      <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
        {query.isLoading || reference.isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : error ? (
          <Alert variant="destructive">
            <AlertTitle>Could not load your application</AlertTitle>
            <AlertDescription>
              {error instanceof Error ? error.message : "Please try again."}
            </AlertDescription>
          </Alert>
        ) : query.data && reference.data ? (
          <>
            <RejectionBanner reason={query.data.rejection_reason} />
            {current !== "welcome" && current !== "status" ? (
              <OnboardingProgress
                steps={query.data.steps}
                current={current}
                nextStep={query.data.next_step}
              />
            ) : null}
            {current === "declarations" || current === "review" ? (
              <SelfDeclaredNotice audience="applicant" />
            ) : null}
            <Outlet context={query.data} />
          </>
        ) : null}
      </div>
    </AppPageFrame>
  )
}
