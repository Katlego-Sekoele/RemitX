import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router"

import { AppPageFrame } from "~/components/app-dashboard/app-page-frame"
import { Button } from "~/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import {
  isKycVerified,
  KYC_ONBOARDING_KEY,
  pathForStep,
} from "~/lib/kyc-onboarding"
import { useApi } from "~/lib/use-api"
import type { Route } from "./+types/index"
import { PageHeader, PageHeaderTitle } from "~/components/ui/page-header"

const ROUTE_MODULE = "routes/app/index.tsx"

export function meta(): Route.MetaDescriptors {
  return [{ title: "Account — RemitX" }, { name: "robots", content: "noindex" }]
}

export default function AppHome() {
  const api = useApi()
  const onboarding = useQuery({
    queryKey: KYC_ONBOARDING_KEY,
    queryFn: api.getKycOnboarding,
  })
  const verified = isKycVerified(onboarding.data?.standing.status)

  return (
    <AppPageFrame module={ROUTE_MODULE}>
      <div className="flex flex-col gap-6">
        <PageHeader>
          <PageHeaderTitle>Account</PageHeaderTitle>
        </PageHeader>
        {!verified && onboarding.data ? (
          <Card>
            <CardHeader>
              <CardTitle>Verification required</CardTitle>
              <CardDescription>
                Finish verification to start sending.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button
                nativeButton={false}
                render={<Link to={pathForStep(onboarding.data.next_step)} />}
              >
                Continue verification
              </Button>
            </CardContent>
          </Card>
        ) : null}
        {verified ? (
          <Card>
            <CardHeader>
              <CardTitle>Ready to send</CardTitle>
              <CardDescription>You&apos;re verified.</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col items-start gap-3">
              <p>No remittances yet.</p>
              <Button
                nativeButton={false}
                variant="outline"
                render={<Link to="/app/beneficiaries" />}
              >
                Manage beneficiaries
              </Button>
            </CardContent>
          </Card>
        ) : null}
      </div>
    </AppPageFrame>
  )
}
