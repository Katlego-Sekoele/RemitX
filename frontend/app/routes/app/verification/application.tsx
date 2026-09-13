import { ArrowLeftIcon, WarningIcon } from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router"

import {
  formatDate,
  formatDateTime,
} from "~/components/admin/kyc-review/format"
import {
  ContactSection,
  FundsSection,
  IdentitySection,
  PepSection,
} from "~/components/kyc/application-sections"
import { KycApplicationDocuments } from "~/components/kyc/kyc-application-documents"
import {
  Timeline,
  TimelineDate,
  TimelineHeader,
  TimelineIndicator,
  TimelineItem,
  TimelineSeparator,
  TimelineTitle,
} from "~/components/reui/timeline"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import {
  DescriptionDetails,
  DescriptionItem,
  DescriptionList,
  DescriptionTerm,
} from "~/components/ui/description-list"
import {
  PageHeader,
  PageHeaderDescription,
  PageHeaderTitle,
} from "~/components/ui/page-header"
import { Skeleton } from "~/components/ui/skeleton"
import { errorMessage } from "~/hooks/use-onboarding"
import {
  applicationStepPath,
  statusCopy,
  statusVariant,
  verificationPath,
} from "~/lib/kyc-onboarding"
import type { Route } from "./+types/application"
import { api, type KycApplicationDetailRead } from "~/client"

/** One application as the applicant sees it: what they declared, what the
 * reviewer may tell them, and how it moved. Read-only unless it is a draft or
 * a reviewer asked for more. */
export default function VerificationApplication({
  params,
}: Route.ComponentProps) {
  const detail = useQuery(
    api.kyc.onboarding.getMyApplication({
      path: { application_id: params.applicationId },
    })
  )

  if (detail.isPending) return <Skeleton className="h-96 w-full" />
  if (detail.isError) {
    return (
      <div className="flex flex-col items-start gap-4">
        <BackToHistory />
        <Alert variant="destructive">
          <WarningIcon />
          <AlertTitle>Could not load this application</AlertTitle>
          <AlertDescription>{errorMessage(detail.error)}</AlertDescription>
        </Alert>
      </div>
    )
  }

  const { application } = detail.data
  const copy = statusCopy(application.status)

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col items-start gap-3">
        <BackToHistory />
        <PageHeader>
          <div className="flex flex-wrap items-center gap-3">
            <PageHeaderTitle>Application</PageHeaderTitle>
            <Badge variant={statusVariant(application.status)}>
              {copy.title}
            </Badge>
          </div>
          <PageHeaderDescription>
            Started {formatDate(application.created_at)}
            {application.submitted_at
              ? ` · Submitted ${formatDate(application.submitted_at)}`
              : ""}
          </PageHeaderDescription>
        </PageHeader>
      </div>

      {detail.data.applicant_message ? (
        <Alert variant="destructive">
          <WarningIcon />
          <AlertTitle>
            {application.status === "more_info_required"
              ? "A reviewer needs something from you"
              : "Not approved"}
          </AlertTitle>
          <AlertDescription>{detail.data.applicant_message}</AlertDescription>
        </Alert>
      ) : null}

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_20rem] xl:grid-cols-[minmax(0,1fr)_22rem]">
        <aside className="flex flex-col gap-4 lg:sticky lg:top-4 lg:order-last">
          <StatusCard detail={detail.data} />
          <StatusHistory detail={detail.data} />
        </aside>

        <div className="flex min-w-0 flex-col gap-4">
          <IdentitySection application={application} />
          <ContactSection application={application} />
          <FundsSection application={application} />
          <PepSection application={application} />
          <KycApplicationDocuments
            applicationId={application.application_id}
            audience="applicant"
          />
        </div>
      </div>
    </div>
  )
}

function StatusCard({ detail }: { detail: KycApplicationDetailRead }) {
  const { application } = detail
  const copy = statusCopy(application.status)

  return (
    <Card>
      <CardHeader>
        <CardTitle>{copy.title}</CardTitle>
        <CardDescription>{copy.body}</CardDescription>
      </CardHeader>
      {application.tier_granted || application.next_review_at ? (
        <CardContent>
          <DescriptionList>
            {application.tier_granted ? (
              <DescriptionItem>
                <DescriptionTerm>Tier</DescriptionTerm>
                <DescriptionDetails>
                  {application.tier_granted}
                </DescriptionDetails>
              </DescriptionItem>
            ) : null}
            {application.next_review_at ? (
              <DescriptionItem>
                <DescriptionTerm>Review due</DescriptionTerm>
                <DescriptionDetails>
                  {formatDate(application.next_review_at)}
                </DescriptionDetails>
              </DescriptionItem>
            ) : null}
          </DescriptionList>
        </CardContent>
      ) : null}
      {detail.editable ? (
        <CardFooter>
          <Button
            className="w-full"
            nativeButton={false}
            render={
              <Link
                to={applicationStepPath(
                  application.application_id,
                  detail.next_step
                )}
              />
            }
          >
            {application.status === "more_info_required"
              ? "Update and resubmit"
              : "Continue"}
          </Button>
        </CardFooter>
      ) : null}
    </Card>
  )
}

/** Status changes only, oldest first — every one has happened, so every step
 * is marked complete. */
function StatusHistory({ detail }: { detail: KycApplicationDetailRead }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>History</CardTitle>
      </CardHeader>
      <CardContent>
        <Timeline value={detail.timeline.length}>
          {detail.timeline.map((event, index) => (
            <TimelineItem key={`${event.status}-${index}`} step={index + 1}>
              <TimelineHeader>
                <TimelineSeparator />
                <TimelineDate dateTime={event.changed_at}>
                  {formatDateTime(event.changed_at)}
                </TimelineDate>
                <TimelineTitle>{statusCopy(event.status).title}</TimelineTitle>
                <TimelineIndicator />
              </TimelineHeader>
            </TimelineItem>
          ))}
        </Timeline>
      </CardContent>
    </Card>
  )
}

function BackToHistory() {
  return (
    <Button
      variant="ghost"
      size="sm"
      nativeButton={false}
      render={<Link to={verificationPath()} />}
    >
      <ArrowLeftIcon data-icon="inline-start" />
      Verification
    </Button>
  )
}
