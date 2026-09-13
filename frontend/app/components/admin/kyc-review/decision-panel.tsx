import { ArrowLeftIcon, PencilSimpleIcon } from "@phosphor-icons/react"
import { useState } from "react"

import {
  ApproveButton,
  RejectForm,
  RequestInfoForm,
} from "~/components/admin/kyc-review/decision-forms"
import {
  PENDING_STATUSES,
  formatDate,
  humanise,
  ratingVariant,
} from "~/components/admin/kyc-review/format"
import { OverrideRatingForm } from "~/components/admin/kyc-review/override-rating-form"
import { SignalBadges } from "~/components/admin/kyc-review/signal-badges"
import { Badge } from "~/components/ui/badge"
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
  DescriptionDetails,
  DescriptionItem,
  DescriptionList,
  DescriptionTerm,
} from "~/components/ui/description-list"
import { Separator } from "~/components/ui/separator"
import type {
  KycApplicationRead,
  KycAssessmentAuditRead,
  KycReasonCodeRead,
  KycRiskRulesRead,
} from "~/client"
import { useHasPermission } from "~/hooks/use-permissions"
import { PERMISSIONS } from "~/lib/permissions"

type Props = {
  application: KycApplicationRead
  latestAssessment: KycAssessmentAuditRead | undefined
  rules: KycRiskRulesRead | undefined
  codes: readonly KycReasonCodeRead[]
  onDecided: () => void
}

/** Everything a reviewer decides with, beside the evidence: the rating, what
 * scored it, and the outcomes in order of consequence. */
export function DecisionPanel({
  application,
  latestAssessment,
  rules,
  codes,
  onDecided,
}: Props) {
  const pending = PENDING_STATUSES.has(application.status)

  return (
    <div className="flex flex-col gap-4">
      <RiskCard
        application={application}
        latestAssessment={latestAssessment}
        rules={rules}
        pending={pending}
      />
      {pending ? (
        <DecisionCard
          application={application}
          codes={codes}
          onDecided={onDecided}
        />
      ) : (
        <OutcomeCard application={application} />
      )}
    </div>
  )
}

function RiskCard({
  application,
  latestAssessment,
  rules,
  pending,
}: Omit<Props, "codes" | "onDecided"> & { pending: boolean }) {
  const canOverride = useHasPermission(PERMISSIONS.kycRiskWrite) && pending
  const [editing, setEditing] = useState(false)
  const ratings = rules?.ratings ?? []

  return (
    <Card>
      <CardHeader>
        <CardTitle>{editing ? "Override rating" : "Risk"}</CardTitle>
        {canOverride && !editing ? (
          <CardAction>
            <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>
              <PencilSimpleIcon data-icon="inline-start" />
              Override
            </Button>
          </CardAction>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <DescriptionList className="sm:grid-cols-2">
          <DescriptionItem>
            <DescriptionTerm>Rating</DescriptionTerm>
            <DescriptionDetails>
              <Badge
                variant={ratingVariant(
                  application.effective_risk_rating,
                  ratings
                )}
                className="capitalize"
              >
                {humanise(application.effective_risk_rating)}
              </Badge>
            </DescriptionDetails>
          </DescriptionItem>
          <DescriptionItem>
            <DescriptionTerm>Score</DescriptionTerm>
            <DescriptionDetails className="tabular-nums">
              {application.risk_score ?? "—"}
            </DescriptionDetails>
          </DescriptionItem>
          {application.risk_rating_override ? (
            <DescriptionItem wide>
              <DescriptionTerm>
                Overridden from {humanise(application.risk_rating)}
              </DescriptionTerm>
              <DescriptionDetails>
                {application.risk_rating_override_reason ?? "—"}
              </DescriptionDetails>
            </DescriptionItem>
          ) : null}
        </DescriptionList>
        {latestAssessment && latestAssessment.matched_signals.length > 0 ? (
          <SignalBadges
            matched={latestAssessment.matched_signals}
            signals={rules?.signals ?? []}
          />
        ) : null}
        {editing ? (
          <>
            <Separator />
            <OverrideRatingForm
              application={application}
              ratings={ratings}
              onDone={() => setEditing(false)}
            />
          </>
        ) : null}
      </CardContent>
    </Card>
  )
}

type Composing = "request_info" | "reject" | null

const COMPOSING_TITLES = {
  request_info: "Request more info",
  reject: "Reject",
} as const

function DecisionCard({
  application,
  codes,
  onDecided,
}: Omit<Props, "latestAssessment" | "rules">) {
  const canDecide = useHasPermission(PERMISSIONS.kycApplicationDecide)
  const canRequestInfo = useHasPermission(PERMISSIONS.kycApplicationRequestInfo)
  const [composing, setComposing] = useState<Composing>(null)

  if (!canDecide && !canRequestInfo) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Decision</CardTitle>
          <CardDescription>You can view this application only.</CardDescription>
        </CardHeader>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          {composing ? COMPOSING_TITLES[composing] : "Decision"}
        </CardTitle>
        {composing ? (
          <CardAction>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setComposing(null)}
            >
              <ArrowLeftIcon data-icon="inline-start" />
              Back
            </Button>
          </CardAction>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {composing === "request_info" ? (
          <RequestInfoForm
            application={application}
            codes={codes}
            onDecided={onDecided}
          />
        ) : composing === "reject" ? (
          <RejectForm
            application={application}
            codes={codes}
            onDecided={onDecided}
          />
        ) : (
          <>
            {canDecide ? (
              <ApproveButton application={application} onDecided={onDecided} />
            ) : null}
            {canRequestInfo ? (
              <Button
                variant="outline"
                className="w-full"
                onClick={() => setComposing("request_info")}
              >
                Request more info
              </Button>
            ) : null}
            {canDecide ? (
              <>
                <Separator className="my-2" />
                <Button
                  variant="destructive"
                  className="w-full"
                  onClick={() => setComposing("reject")}
                >
                  Reject
                </Button>
              </>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  )
}

function OutcomeCard({ application }: { application: KycApplicationRead }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Outcome</CardTitle>
      </CardHeader>
      <CardContent>
        <DescriptionList className="sm:grid-cols-2">
          <DescriptionItem>
            <DescriptionTerm>Status</DescriptionTerm>
            <DescriptionDetails className="capitalize">
              {humanise(application.status)}
            </DescriptionDetails>
          </DescriptionItem>
          <DescriptionItem>
            <DescriptionTerm>Updated</DescriptionTerm>
            <DescriptionDetails>
              {formatDate(application.updated_at)}
            </DescriptionDetails>
          </DescriptionItem>
          {application.tier_granted != null ? (
            <DescriptionItem>
              <DescriptionTerm>Tier granted</DescriptionTerm>
              <DescriptionDetails>
                {application.tier_granted}
              </DescriptionDetails>
            </DescriptionItem>
          ) : null}
          {application.next_review_at ? (
            <DescriptionItem>
              <DescriptionTerm>Next review</DescriptionTerm>
              <DescriptionDetails>
                {formatDate(application.next_review_at)}
              </DescriptionDetails>
            </DescriptionItem>
          ) : null}
        </DescriptionList>
      </CardContent>
    </Card>
  )
}
