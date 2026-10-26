import { ArrowSquareOutIcon } from "@phosphor-icons/react"
import { format } from "date-fns"

import {
  Timeline,
  TimelineContent,
  TimelineHeader,
  TimelineIndicator,
  TimelineItem,
  TimelineSeparator,
  TimelineTitle,
} from "~/components/reui/timeline"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import {
  Card,
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
import { formatMoney } from "~/lib/money"
import {
  explorerTxUrl,
  payoutProofHash,
  PAYOUT_FAILED_DETAIL,
  PAYOUT_STAGE_LABELS,
  payoutStage,
  roundLabel,
  type PayoutStage,
  type StokvelRoundRead,
} from "~/lib/stokvels"

const STEPS: { stage: PayoutStage; title: string }[] = [
  { stage: "collecting", title: "Everyone paid" },
  { stage: "released", title: "Pool released" },
  { stage: "sending", title: "Sending" },
  { stage: "delivered", title: "Delivered" },
]

function stepNumber(stage: PayoutStage): number {
  if (stage === "failed") return 3
  return STEPS.findIndex((step) => step.stage === stage) + 1
}

/**
 * A round's payout, parcel-tracker style: Everyone paid → Pool released →
 * Sending to the beneficiary → Delivered. The hashes are "proof of payment"
 * links; the technical names stay out of the copy (product docx §2).
 */
export function PayoutStatus({
  round,
  totalRounds,
  recipientName,
  beneficiaryName,
  payoutCurrency,
  currency,
  pool,
  paid,
  members,
  outstandingNames,
}: {
  round: StokvelRoundRead
  totalRounds: number
  recipientName: string
  beneficiaryName: string | null
  payoutCurrency: string | null
  currency: string
  /** Members × today's fiat estimate. Null when the rate is missing.
   * `round.pool_fiat_amount` stays null until #241. */
  pool: string | null
  paid: number
  members: number
  outstandingNames: string[]
}) {
  const everyonePaid = paid >= members
  const stage = payoutStage(round, everyonePaid)
  const active = stepNumber(stage)
  const to = beneficiaryName ?? `${recipientName}'s beneficiary`
  const sendingTitle = `Sending to ${to}`
  const proof = payoutProofHash(round)
  const poolShown = round.pool_fiat_amount ?? pool

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <CardTitle>
            {roundLabel(round.round, totalRounds)} payout · {recipientName}
          </CardTitle>
          <Badge
            variant={
              stage === "delivered"
                ? "default"
                : stage === "failed"
                  ? "destructive"
                  : "secondary"
            }
          >
            {PAYOUT_STAGE_LABELS[stage]}
          </Badge>
        </div>
        <CardDescription>
          {stage === "collecting"
            ? outstandingNames.length > 0
              ? `Waiting for ${outstandingNames.join(", ")}. The payout can be released after ${format(new Date(round.payout_time), "EEE d MMM HH:mm")}, once everyone has paid.`
              : `Releases on ${format(new Date(round.payout_time), "EEE d MMM 'at' HH:mm")}.`
            : stage === "delivered"
              ? `${to} received the payout${payoutCurrency ? ` in ${payoutCurrency}` : ""}.`
              : stage === "failed"
                ? PAYOUT_FAILED_DETAIL
                : "Exchange rate is fixed when the payout is sent."}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <DescriptionList>
          <DescriptionItem>
            <DescriptionTerm>Pool ({members} × member)</DescriptionTerm>
            <DescriptionDetails>
              {poolShown
                ? formatMoney(poolShown, currency)
                : "Today's rate is unavailable"}
            </DescriptionDetails>
          </DescriptionItem>
          {round.remittance_id ? (
            <DescriptionItem>
              <DescriptionTerm>Reference</DescriptionTerm>
              <DescriptionDetails>
                <code className="font-mono">{round.remittance_id}</code>
              </DescriptionDetails>
            </DescriptionItem>
          ) : null}
          {proof ? (
            <DescriptionItem>
              <DescriptionTerm>Proof of payment</DescriptionTerm>
              <DescriptionDetails>
                <Button
                  variant="link"
                  size="xs"
                  nativeButton={false}
                  render={
                    <a
                      href={explorerTxUrl(proof)}
                      target="_blank"
                      rel="noreferrer"
                    />
                  }
                >
                  View on the explorer
                  <ArrowSquareOutIcon
                    data-icon="inline-end"
                    aria-hidden="true"
                  />
                </Button>
              </DescriptionDetails>
            </DescriptionItem>
          ) : null}
        </DescriptionList>
        <Timeline value={active}>
          {STEPS.map((step, index) => (
            <TimelineItem key={step.stage} step={index + 1}>
              <TimelineHeader>
                <TimelineSeparator />
                <TimelineTitle>
                  {step.stage === "sending" ? sendingTitle : step.title}
                </TimelineTitle>
                <TimelineIndicator />
              </TimelineHeader>
              <TimelineContent>
                {step.stage === "collecting"
                  ? `${paid} of ${members} contributions confirmed`
                  : step.stage === "released"
                    ? `Released ${format(new Date(round.payout_time), "EEE d MMM, HH:mm")}`
                    : step.stage === "sending"
                      ? stage === "failed"
                        ? PAYOUT_STAGE_LABELS.failed
                        : "At the rate on payout day"
                      : payoutCurrency
                        ? `Paid out in ${payoutCurrency}`
                        : ""}
              </TimelineContent>
            </TimelineItem>
          ))}
        </Timeline>
      </CardContent>
    </Card>
  )
}
