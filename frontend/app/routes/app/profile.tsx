import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router"

import { AppPageFrame } from "~/components/app-dashboard/app-page-frame"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import {
  Card,
  CardAction,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import { PageHeader, PageHeaderTitle } from "~/components/ui/page-header"
import {
  statusCopy,
  statusVariant,
  verificationPath,
} from "~/lib/kyc-onboarding"
import type { Route } from "./+types/profile"
import { api } from "~/client"

const ROUTE_MODULE = "routes/app/profile.tsx"

export function meta(): Route.MetaDescriptors {
  return [{ title: "Profile — RemitX" }, { name: "robots", content: "noindex" }]
}

export default function ProfilePage() {
  const onboarding = useQuery(api.kyc.onboarding.getApplication())
  const status = onboarding.data?.standing.status

  return (
    <AppPageFrame module={ROUTE_MODULE}>
      <div className="flex flex-col gap-6">
        <PageHeader>
          <PageHeaderTitle>Profile</PageHeaderTitle>
        </PageHeader>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              Verification
              {status ? (
                <Badge variant={statusVariant(status)}>
                  {statusCopy(status).title}
                </Badge>
              ) : null}
            </CardTitle>
            <CardDescription>
              Your identity verification and past applications.
            </CardDescription>
            <CardAction>
              <Button
                variant="outline"
                nativeButton={false}
                render={<Link to={verificationPath()} />}
              >
                View
              </Button>
            </CardAction>
          </CardHeader>
        </Card>
      </div>
    </AppPageFrame>
  )
}
