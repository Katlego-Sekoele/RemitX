import { WarningIcon } from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"
import { Navigate, Outlet, useLocation } from "react-router"

import { OnboardingProgress } from "~/components/kyc/onboarding-progress"
import { SelfDeclaredNotice } from "~/components/kyc/self-declared-notice"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { Skeleton } from "~/components/ui/skeleton"
import { errorMessage } from "~/hooks/use-onboarding"
import { applicationPath } from "~/lib/kyc-onboarding"
import type { Route } from "./+types/steps-layout"
import { api } from "~/client"

/** The wizard for one application. Only an editable application has steps;
 * anything else is sent to its read-only detail page. */
export default function StepsLayout({ params }: Route.ComponentProps) {
  const { pathname } = useLocation()
  const current = pathname.split("/").at(-1) ?? ""
  const query = useQuery(
    api.kyc.onboarding.getMyApplication({
      path: { application_id: params.applicationId },
    })
  )

  if (query.isPending) {
    return <Skeleton className="mx-auto h-40 w-full max-w-2xl" />
  }
  if (query.isError) {
    return (
      <Alert variant="destructive" className="mx-auto max-w-2xl">
        <AlertTitle>Could not load your application</AlertTitle>
        <AlertDescription>{errorMessage(query.error)}</AlertDescription>
      </Alert>
    )
  }

  const detail = query.data
  if (!detail.editable) {
    return <Navigate to={applicationPath(params.applicationId)} replace />
  }

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
      {detail.applicant_message ? (
        <Alert variant="destructive">
          <WarningIcon />
          <AlertTitle>A reviewer needs something from you</AlertTitle>
          <AlertDescription>{detail.applicant_message}</AlertDescription>
        </Alert>
      ) : null}
      <OnboardingProgress
        applicationId={params.applicationId}
        steps={detail.steps}
        current={current}
        nextStep={detail.next_step}
      />
      {current === "declarations" || current === "review" ? (
        <SelfDeclaredNotice audience="applicant" />
      ) : null}
      <Outlet context={detail} />
    </div>
  )
}
