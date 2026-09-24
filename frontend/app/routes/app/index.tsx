import { PaperPlaneTiltIcon } from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router"

import { BalanceSummary } from "~/components/accounts/balance-summary"
import { AppPageFrame } from "~/components/app-dashboard/app-page-frame"
import { RecentTransfers } from "~/components/transfers/recent-transfers"
import { Button } from "~/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import { SEND_HREF } from "~/lib/accounts"
import { isKycVerified, verificationPath } from "~/lib/kyc-onboarding"
import { SEND_PATH } from "~/lib/send"
import { TRANSFERS_PATH } from "~/lib/transfers"
import type { Route } from "./+types/index"
import { PageHeader, PageHeaderTitle } from "~/components/ui/page-header"
import { api } from "~/client"

const ROUTE_MODULE = "routes/app/index.tsx"
const RECENT_LIMIT = 5

export function meta(): Route.MetaDescriptors {
  return [{ title: "Account — RemitX" }, { name: "robots", content: "noindex" }]
}

export default function AppHome() {
  const onboarding = useQuery(api.kyc.onboarding.getApplication())
  const verified = isKycVerified(onboarding.data?.standing.status)

  return (
    <AppPageFrame module={ROUTE_MODULE}>
      <div className="flex flex-col gap-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <PageHeader>
            <PageHeaderTitle>Overview</PageHeaderTitle>
          </PageHeader>
          <Button nativeButton={false} render={<Link to={SEND_HREF} />}>
            <PaperPlaneTiltIcon data-icon="inline-start" />
            Send money
          </Button>
        </div>
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
                render={<Link to={verificationPath()} />}
              >
                Continue verification
              </Button>
            </CardContent>
          </Card>
        ) : null}
        <BalanceSummary />
        {verified ? (
          <Card>
            <CardHeader>
              <CardTitle>Ready to send</CardTitle>
              <CardDescription>You&apos;re verified.</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col items-start gap-3">
              <div className="flex flex-wrap gap-2">
                <Button nativeButton={false} render={<Link to={SEND_PATH} />}>
                  Send money
                </Button>
                <Button
                  nativeButton={false}
                  variant="outline"
                  render={<Link to="/app/beneficiaries" />}
                >
                  Manage beneficiaries
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : null}
        {onboarding.data ? (
          <Card>
            <CardHeader>
              <CardTitle>Recent transfers</CardTitle>
              <CardDescription>
                Your last {RECENT_LIMIT}, sent and received.
              </CardDescription>
              <CardAction>
                <Button
                  nativeButton={false}
                  variant="link"
                  render={<Link to={TRANSFERS_PATH} />}
                >
                  See all
                </Button>
              </CardAction>
            </CardHeader>
            <CardContent>
              <RecentTransfers limit={RECENT_LIMIT} />
            </CardContent>
          </Card>
        ) : null}
      </div>
    </AppPageFrame>
  )
}
