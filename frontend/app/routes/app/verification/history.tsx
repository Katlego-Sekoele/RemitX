import {
  CaretRightIcon,
  IdentificationBadgeIcon,
  PlusIcon,
} from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router"

import { formatDate } from "~/components/admin/kyc-review/format"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import {
  Card,
  CardAction,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "~/components/ui/empty"
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
} from "~/components/ui/item"
import {
  PageHeader,
  PageHeaderDescription,
  PageHeaderTitle,
} from "~/components/ui/page-header"
import { Skeleton } from "~/components/ui/skeleton"
import { errorMessage } from "~/hooks/use-onboarding"
import {
  applicationPath,
  canStartApplication,
  newApplicationPath,
  statusCopy,
  statusVariant,
} from "~/lib/kyc-onboarding"
import { api, type KycApplicationSummaryRead } from "~/client"

export default function VerificationHistory() {
  const standing = useQuery(api.kyc.onboarding.getApplication())
  const history = useQuery(api.kyc.onboarding.listMyApplications())

  if (standing.isPending || history.isPending) {
    return <Skeleton className="h-64 w-full" />
  }
  if (standing.isError || history.isError) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Could not load your verification</AlertTitle>
        <AlertDescription>
          {errorMessage(standing.error ?? history.error)}
        </AlertDescription>
      </Alert>
    )
  }

  const status = standing.data.standing.status
  const open = history.data.find((application) => application.editable)
  const canStart = canStartApplication(status)
  const copy = statusCopy(status)

  return (
    <div className="flex flex-col gap-6">
      <PageHeader>
        <PageHeaderTitle>Verification</PageHeaderTitle>
        <PageHeaderDescription>
          Your identity verification and past applications.
        </PageHeaderDescription>
      </PageHeader>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {copy.title}
            {standing.data.standing.tier > 0 ? (
              <Badge variant="outline">
                Tier {standing.data.standing.tier}
              </Badge>
            ) : null}
          </CardTitle>
          <CardDescription>{copy.body}</CardDescription>
          <CardAction>
            {open ? (
              <Button
                nativeButton={false}
                render={<Link to={applicationPath(open.application_id)} />}
              >
                Continue
              </Button>
            ) : canStart ? (
              <Button
                nativeButton={false}
                render={<Link to={newApplicationPath()} />}
              >
                <PlusIcon data-icon="inline-start" />
                Start new application
              </Button>
            ) : null}
          </CardAction>
        </CardHeader>
      </Card>

      {history.data.length === 0 ? (
        <Empty className="border">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <IdentificationBadgeIcon />
            </EmptyMedia>
            <EmptyTitle>No applications yet</EmptyTitle>
            <EmptyDescription>Takes about five minutes.</EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button
              nativeButton={false}
              render={<Link to={newApplicationPath()} />}
            >
              Start verification
            </Button>
          </EmptyContent>
        </Empty>
      ) : (
        <ItemGroup className="gap-2">
          {history.data.map((application) => (
            <ApplicationItem
              key={application.application_id}
              application={application}
            />
          ))}
        </ItemGroup>
      )}
    </div>
  )
}

function ApplicationItem({
  application,
}: {
  application: KycApplicationSummaryRead
}) {
  const dates = [
    `Started ${formatDate(application.created_at)}`,
    application.submitted_at
      ? `submitted ${formatDate(application.submitted_at)}`
      : null,
    application.decided_at
      ? `decided ${formatDate(application.decided_at)}`
      : null,
  ].filter(Boolean)

  return (
    <Item
      variant="outline"
      render={<Link to={applicationPath(application.application_id)} />}
    >
      <ItemContent>
        <ItemTitle>
          <Badge variant={statusVariant(application.status)}>
            {statusCopy(application.status).title}
          </Badge>
        </ItemTitle>
        <ItemDescription>{dates.join(", ")}</ItemDescription>
      </ItemContent>
      <ItemActions>
        <CaretRightIcon aria-hidden="true" />
      </ItemActions>
    </Item>
  )
}
