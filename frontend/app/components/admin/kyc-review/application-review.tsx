import { ArrowLeftIcon, EyeIcon, WarningIcon } from "@phosphor-icons/react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { Link, useNavigate } from "react-router"

import { KycApplicationDocuments } from "~/components/admin/kyc-application-documents"
import { DecisionPanel } from "~/components/admin/kyc-review/decision-panel"
import {
  ContactSection,
  FundsSection,
  IdentitySection,
  PepSection,
} from "~/components/admin/kyc-review/detail-sections"
import {
  QUEUE_HREF,
  errorMessage,
  formatDate,
  humanise,
  invalidateApplication,
  ratingVariant,
} from "~/components/admin/kyc-review/format"
import { RiskHistory } from "~/components/admin/kyc-review/risk-history"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import {
  PageHeader,
  PageHeaderDescription,
  PageHeaderTitle,
} from "~/components/ui/page-header"
import { Skeleton } from "~/components/ui/skeleton"
import {
  api,
  type KycApplicationRead,
  type KycApplicationReadPii,
  type KycRiskRulesRead,
} from "~/client"
import { useHasPermission } from "~/hooks/use-permissions"
import { PERMISSIONS } from "~/lib/permissions"

/** One application, laid out for a decision: the evidence on the left, the
 * rating and outcomes beside it. Opening a submitted application claims it. */
export function ApplicationReview({
  applicationId,
  onApplicantName,
}: {
  applicationId: string
  onApplicantName: (name: string | null) => void
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const canRequestInfo = useHasPermission(PERMISSIONS.kycApplicationRequestInfo)
  const [unmasked, setUnmasked] = useState<KycApplicationReadPii | null>(null)
  const path = { path: { application_id: applicationId } }

  const detail = useQuery(api.admin.kyc.applications.getReviewApplication(path))
  const audit = useQuery(api.admin.kyc.applications.listAssessmentAudit(path))
  const rules = useQuery(api.admin.kyc.applications.getRiskRules())
  const codes = useQuery(api.admin.kyc.applications.listReasonCodes())

  const claim = useMutation({
    ...api.admin.kyc.applications.startApplicationReview(),
    onSuccess: (data) => {
      queryClient.setQueryData(
        api.admin.kyc.applications.getReviewApplication(path).queryKey,
        data
      )
      invalidateApplication(queryClient, applicationId)
    },
  })

  useEffect(() => {
    const application = detail.data
    if (
      application?.status === "submitted" &&
      canRequestInfo &&
      !claim.isPending &&
      !claim.isError &&
      !claim.isSuccess
    ) {
      claim.mutate({
        path: { application_id: application.application_id },
        body: { expected_version: application.version },
      })
    }
  }, [applicationId, canRequestInfo, detail.data?.status, detail.data?.version])

  // Masked until revealed — the breadcrumb shows what the page shows.
  const applicantName = (unmasked ?? detail.data)?.full_name ?? null
  useEffect(() => {
    onApplicantName(applicantName)
  }, [applicantName])

  if (detail.isPending) return <ReviewSkeleton />
  if (detail.isError || !detail.data) {
    return (
      <div className="flex flex-col items-start gap-4">
        <BackToQueue />
        <Alert variant="destructive">
          <WarningIcon />
          <AlertTitle>Could not load this application</AlertTitle>
          <AlertDescription>{errorMessage(detail.error)}</AlertDescription>
        </Alert>
      </div>
    )
  }

  const shown = unmasked ?? detail.data
  const entries = audit.data

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col items-start gap-3">
        <BackToQueue />
        <ReviewHeader application={shown} rules={rules.data} />
      </div>

      {claim.isError ? (
        <Alert variant="destructive">
          <WarningIcon />
          <AlertTitle>Could not start review</AlertTitle>
          <AlertDescription>{errorMessage(claim.error)}</AlertDescription>
        </Alert>
      ) : null}

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_20rem] xl:grid-cols-[minmax(0,1fr)_22rem]">
        <aside className="flex flex-col gap-4 lg:sticky lg:top-4 lg:order-last">
          <DecisionPanel
            // Decisions carry the version the server issued, masked or not.
            application={detail.data}
            latestAssessment={entries?.at(-1)}
            rules={rules.data}
            codes={codes.data ?? []}
            onDecided={() => navigate(QUEUE_HREF)}
          />
        </aside>

        <div className="flex min-w-0 flex-col gap-4">
          <IdentitySection
            application={shown}
            revealAction={
              unmasked === null ? (
                <RevealButton
                  applicationId={applicationId}
                  onRevealed={setUnmasked}
                />
              ) : null
            }
          />
          <ContactSection application={shown} />
          <FundsSection application={shown} />
          <PepSection application={shown} />
          <KycApplicationDocuments applicationId={applicationId} />
          <RiskHistory
            entries={entries}
            loading={audit.isPending}
            error={audit.isError ? audit.error : null}
            signals={rules.data?.signals ?? []}
          />
        </div>
      </div>
    </div>
  )
}

function BackToQueue() {
  return (
    <Button
      variant="ghost"
      size="sm"
      nativeButton={false}
      render={<Link to={QUEUE_HREF} />}
    >
      <ArrowLeftIcon data-icon="inline-start" />
      Queue
    </Button>
  )
}

function ReviewHeader({
  application,
  rules,
}: {
  application: KycApplicationRead | KycApplicationReadPii
  rules: KycRiskRulesRead | undefined
}) {
  return (
    <PageHeader>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <PageHeaderTitle>
          {application.full_name ?? "Applicant"}
        </PageHeaderTitle>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="outline" className="capitalize">
            {humanise(application.status)}
          </Badge>
          {application.effective_risk_rating ? (
            <Badge
              variant={ratingVariant(
                application.effective_risk_rating,
                rules?.ratings ?? []
              )}
              className="capitalize"
            >
              {humanise(application.effective_risk_rating)} risk
            </Badge>
          ) : null}
          {application.declares_pep ? (
            <Badge variant="destructive">PEP</Badge>
          ) : null}
        </div>
      </div>
      <PageHeaderDescription>
        Submitted {formatDate(application.submitted_at)}
        {application.reviewer_user_id ? " · Claimed for review" : ""}
      </PageHeaderDescription>
    </PageHeader>
  )
}

function RevealButton({
  applicationId,
  onRevealed,
}: {
  applicationId: string
  onRevealed: (value: KycApplicationReadPii) => void
}) {
  const canReveal = useHasPermission(PERMISSIONS.kycApplicationReadPii)
  const reveal = useMutation({
    ...api.admin.kyc.applications.revealApplicationPii(),
    onSuccess: onRevealed,
  })

  if (!canReveal) return null

  return (
    <Button
      variant={reveal.isError ? "destructive" : "outline"}
      size="sm"
      title={reveal.isError ? errorMessage(reveal.error) : undefined}
      onClick={() => reveal.mutate({ path: { application_id: applicationId } })}
      disabled={reveal.isPending}
    >
      <EyeIcon data-icon="inline-start" />
      {reveal.isPending
        ? "Revealing…"
        : reveal.isError
          ? "Retry reveal"
          : "Reveal"}
    </Button>
  )
}

function ReviewSkeleton() {
  return (
    <div className="flex flex-col gap-6">
      <Skeleton className="h-16 w-72" />
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <Skeleton className="h-96 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    </div>
  )
}
