import { ArrowClockwiseIcon, UsersFourIcon } from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"
import { format } from "date-fns"
import { Link, useParams } from "react-router"

import { AppPageFrame } from "~/components/app-dashboard/app-page-frame"
import {
  Alert,
  AlertAction,
  AlertDescription,
  AlertTitle,
} from "~/components/ui/alert"
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
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "~/components/ui/empty"
import {
  PageHeader,
  PageHeaderDescription,
  PageHeaderTitle,
} from "~/components/ui/page-header"
import { Skeleton } from "~/components/ui/skeleton"
import { errorMessage } from "~/hooks/use-onboarding"
import { formatMoney } from "~/lib/money"
import {
  currentRecipientId,
  paidMemberIds,
  PHASE_LABELS,
  poolAmount,
  roundLabel,
  stokvelQueries,
  stokvelsPath,
  type StokvelDetailRead,
} from "~/lib/stokvels"
import type { Route } from "./+types/stokvel"

// Nested under the Stokvels sidebar entry: that module owns the title.
const ROUTE_MODULE = "routes/app/stokvels.tsx"

export function meta(): Route.MetaDescriptors {
  return [{ title: "Stokvel — RemitX" }, { name: "robots", content: "noindex" }]
}

/**
 * One stokvel (R4-02 scaffold, #251). Shows the mocked member view; the
 * contribution flow, payout status and hashes are R4-05 (#254), the
 * organiser setup is R4-06 (#255).
 */
export default function StokvelPage() {
  const { stokvelId = "" } = useParams()
  const detail = useQuery({
    ...stokvelQueries.detail(stokvelId),
    enabled: Boolean(stokvelId),
  })

  const parents = [{ label: "Stokvels", href: stokvelsPath() }]

  if (detail.isPending) {
    return (
      <AppPageFrame module={ROUTE_MODULE} title="Stokvel" parents={parents}>
        <div className="flex flex-col gap-4">
          <Skeleton className="h-10 w-64" />
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      </AppPageFrame>
    )
  }

  if (detail.isError) {
    return (
      <AppPageFrame module={ROUTE_MODULE} title="Stokvel" parents={parents}>
        <Empty className="border">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <UsersFourIcon />
            </EmptyMedia>
            <EmptyTitle>Couldn&apos;t open this stokvel</EmptyTitle>
            <EmptyDescription>{errorMessage(detail.error)}</EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button
              variant="outline"
              size="sm"
              disabled={detail.isFetching}
              onClick={() => detail.refetch()}
            >
              <ArrowClockwiseIcon data-icon="inline-start" />
              Retry
            </Button>
            <Button
              variant="ghost"
              size="sm"
              nativeButton={false}
              render={<Link to={stokvelsPath()} />}
            >
              Back to stokvels
            </Button>
          </EmptyContent>
        </Empty>
      </AppPageFrame>
    )
  }

  return (
    <AppPageFrame
      module={ROUTE_MODULE}
      title={detail.data.name}
      parents={parents}
    >
      <StokvelDetail stokvel={detail.data} />
    </AppPageFrame>
  )
}

function StokvelDetail({ stokvel }: { stokvel: StokvelDetailRead }) {
  const cycle = stokvel.cycle
  const active = cycle?.status === "active"
  const paid = paidMemberIds(stokvel)
  const recipientId = currentRecipientId(cycle)
  const currentRound = active ? cycle.rounds[cycle.current_round] : undefined
  const pool = poolAmount(
    stokvel.contribution_fiat_estimate,
    stokvel.member_count
  )
  const memberName = (memberId: string) =>
    stokvel.members.find((m) => m.member_id === memberId)?.full_name ?? "Member"

  return (
    <div className="flex flex-col gap-6">
      <PageHeader>
        <div className="flex flex-wrap items-center gap-3">
          <PageHeaderTitle>{stokvel.name}</PageHeaderTitle>
          <Badge variant={active ? "default" : "outline"}>
            {active
              ? roundLabel(cycle.current_round, cycle.total_rounds)
              : PHASE_LABELS[stokvel.phase]}
          </Badge>
        </div>
        <PageHeaderDescription>
          {formatMoney(stokvel.contribution_fiat_estimate, stokvel.currency)}{" "}
          per member each round · pool {formatMoney(pool, stokvel.currency)} ·
          organised by {stokvel.is_organiser ? "you" : stokvel.organiser_name}
        </PageHeaderDescription>
      </PageHeader>

      {active && currentRound ? (
        <Card>
          <CardHeader>
            <CardTitle>Your contribution</CardTitle>
            <CardDescription>
              {paid.has(stokvel.my_member_id)
                ? "Paid for this round."
                : `Due ${format(new Date(currentRound.deadline), "EEE d MMM")} · payout ${format(new Date(currentRound.payout_time), "EEE d MMM, HH:mm")}`}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap items-center justify-between gap-3">
            <span className="font-heading text-3xl font-bold tabular-nums">
              {formatMoney(
                stokvel.contribution_fiat_estimate,
                stokvel.currency
              )}
            </span>
            {/* The pay flow and its error states arrive in #254. */}
            <Button disabled={paid.has(stokvel.my_member_id)}>
              {paid.has(stokvel.my_member_id) ? "Paid" : "Pay now"}
            </Button>
          </CardContent>
        </Card>
      ) : stokvel.phase === "forming" ? (
        <Card>
          <CardHeader>
            <CardTitle>Setting up</CardTitle>
            <CardDescription>
              {stokvel.invitations.length} invitation
              {stokvel.invitations.length === 1 ? "" : "s"} pending ·{" "}
              {stokvel.my_beneficiary
                ? `your payout goes to ${stokvel.my_beneficiary.full_name}`
                : "choose a payout beneficiary to be ready"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {/* Beneficiary picker, payout order and Start cycle: #255. */}
            <Button variant="outline" disabled>
              {stokvel.is_organiser ? "Start cycle" : "Choose beneficiary"}
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {cycle ? (
        <Card>
          <CardHeader>
            <CardTitle>Payout order</CardTitle>
            <CardDescription>
              {active
                ? `${paid.size} of ${stokvel.member_count} paid this round`
                : `Cycle ${cycle.cycle_number} · ${PHASE_LABELS[cycle.status]}`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ol className="flex flex-col gap-2">
              {cycle.payout_order.map((memberId, round) => {
                const name =
                  memberId === stokvel.my_member_id
                    ? "You"
                    : memberName(memberId)
                const roundRead = cycle.rounds[round]
                return (
                  <li
                    key={memberId}
                    className="flex flex-wrap items-center justify-between gap-2 text-sm"
                  >
                    <span>
                      {round + 1}. {name}
                      {memberId === recipientId ? (
                        <Badge variant="default" className="ml-2">
                          Next
                        </Badge>
                      ) : null}
                    </span>
                    <span className="text-muted-foreground">
                      {roundRead?.release_status === "released"
                        ? "Paid out"
                        : roundRead
                          ? format(new Date(roundRead.payout_time), "EEE d MMM")
                          : ""}
                    </span>
                  </li>
                )
              })}
            </ol>
          </CardContent>
        </Card>
      ) : null}

      {stokvel.members.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Members</CardTitle>
            {active ? (
              <CardDescription>
                If one member hasn&apos;t paid, the payout waits for them.
              </CardDescription>
            ) : null}
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-2">
              {stokvel.members.map((member) => (
                <li
                  key={member.member_id}
                  className="flex items-center justify-between gap-2 text-sm"
                >
                  <span>
                    {member.is_me ? "You" : member.full_name}
                    {member.is_organiser ? (
                      <span className="text-muted-foreground">
                        {" "}
                        · organiser
                      </span>
                    ) : null}
                  </span>
                  {active ? (
                    <Badge
                      variant={
                        paid.has(member.member_id) ? "default" : "secondary"
                      }
                    >
                      {paid.has(member.member_id) ? "Paid" : "Waiting"}
                    </Badge>
                  ) : null}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
