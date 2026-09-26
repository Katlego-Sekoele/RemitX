import { useUser } from "@clerk/react-router"
import {
  IdentificationCardIcon,
  PaperPlaneTiltIcon,
} from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router"

import { BalanceSummary } from "~/components/accounts/balance-summary"
import { AppPageFrame } from "~/components/app-dashboard/app-page-frame"
import { DashboardInsights } from "~/components/dashboard/dashboard-insights"
import { ConnectedWorldIllustration } from "~/components/illustrations/connected-world"
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
import {
  PageHeader,
  PageHeaderDescription,
  PageHeaderTitle,
} from "~/components/ui/page-header"
import { isKycVerified, verificationPath } from "~/lib/kyc-onboarding"
import { SEND_PATH } from "~/lib/send"
import { TRANSFERS_PATH } from "~/lib/transfers"
import type { Route } from "./+types/index"
import { api } from "~/client"

const ROUTE_MODULE = "routes/app/index.tsx"
const RECENT_LIMIT = 5

export function meta(): Route.MetaDescriptors {
  return [{ title: "Account — RemitX" }, { name: "robots", content: "noindex" }]
}

export default function AppHome() {
  const onboarding = useQuery(api.kyc.onboarding.getApplication())
  const verified = isKycVerified(onboarding.data?.standing)

  return (
    <AppPageFrame module={ROUTE_MODULE}>
      <div className="flex flex-col gap-6">
        <Welcome verified={verified} loaded={onboarding.data !== undefined} />
        <BalanceSummary />
        <DashboardInsights />
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

/** The greeting, and the one thing to do next: verify, or send. */
function Welcome({ verified, loaded }: { verified: boolean; loaded: boolean }) {
  const { user } = useUser()
  const name = user?.firstName
  const greeting = verified ? "Welcome back" : "Welcome to RemitX"

  return (
    <Card>
      <CardContent className="flex flex-col-reverse items-center gap-6 sm:flex-row sm:justify-between">
        <div className="flex w-full flex-col items-start gap-4">
          <PageHeader>
            <PageHeaderTitle>
              {name ? `${greeting}, ${name}` : greeting}
            </PageHeaderTitle>
            <PageHeaderDescription>
              {verified
                ? "You're verified and ready to send money to family and friends across borders."
                : "Send money to family and friends across borders. Verify your identity to get started."}
            </PageHeaderDescription>
          </PageHeader>
          {!loaded ? null : verified ? (
            <div className="flex flex-wrap gap-2">
              <Button nativeButton={false} render={<Link to={SEND_PATH} />}>
                <PaperPlaneTiltIcon data-icon="inline-start" />
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
          ) : (
            <Button
              nativeButton={false}
              render={<Link to={verificationPath()} />}
            >
              <IdentificationCardIcon data-icon="inline-start" />
              Continue verification
            </Button>
          )}
        </div>
        <ConnectedWorldIllustration className="h-auto w-full max-w-60 shrink-0" />
      </CardContent>
    </Card>
  )
}
