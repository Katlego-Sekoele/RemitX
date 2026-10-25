import { ArrowClockwiseIcon, UsersFourIcon } from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"
import { Link, useParams } from "react-router"

import { api } from "~/client"
import { AppPageFrame } from "~/components/app-dashboard/app-page-frame"
import { ContributionPanel } from "~/components/stokvels/contribution-panel"
import { CycleSetup } from "~/components/stokvels/cycle-setup"
import { InviteMemberForm } from "~/components/stokvels/invite-member-form"
import { PayoutBeneficiaryCard } from "~/components/stokvels/payout-beneficiary-card"
import { PayoutStatus } from "~/components/stokvels/payout-status"
import { PotRing } from "~/components/stokvels/pot-ring"
import {
  PayoutQueue,
  RoundSchedule,
} from "~/components/stokvels/round-schedule"
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
  canInvite,
  firstNameOf,
  myCurrentContribution,
  openRound,
  outstandingMembers,
  paidMemberIds,
  pendingInvitations,
  plannedPayoutOrder,
  PHASE_LABELS,
  poolAmount,
  roundLabel,
  stokvelQueries,
  stokvelsPath,
  type StokvelDetailRead,
  type StokvelMemberRead,
} from "~/lib/stokvels"
import type { Route } from "./+types/stokvel"

// Nested under the Stokvels sidebar entry: that module owns the title.
const ROUTE_MODULE = "routes/app/stokvels.tsx"

export function meta(): Route.MetaDescriptors {
  return [{ title: "Stokvel — RemitX" }, { name: "robots", content: "noindex" }]
}

/**
 * One stokvel, the member screen (R4-05, #254): pot, your contribution and
 * the pay flow, the current round's payout, payout order, members and the
 * round history, from `GET /stokvels/{id}` (#236).
 * The organiser's setup (beneficiary, order, start cycle) is R4-06 (#255).
 */
export default function StokvelPage() {
  const { stokvelId = "" } = useParams()
  const detail = useQuery({
    ...stokvelQueries.detail(stokvelId),
    enabled: Boolean(stokvelId),
    // A contribution confirms on chain a few seconds after it is sent.
    refetchInterval: (query) => {
      if (query.state.status === "error") return false
      const data = query.state.data
      if (!data) return false
      const inflight = data.contributions.some(
        (contribution) =>
          contribution.member_id === data.my_member_id &&
          (contribution.status === "pending" ||
            contribution.status === "processing")
      )
      return inflight ? 1500 : false
    },
  })
  const accounts = useQuery(api.accounts.getAccounts())

  const parents = [{ label: "Stokvels", href: stokvelsPath() }]

  if (detail.isPending) {
    return (
      <AppPageFrame module={ROUTE_MODULE} title="Stokvel" parents={parents}>
        <div className="flex flex-col gap-4">
          <Skeleton className="h-10 w-64" />
          <Skeleton className="h-56 w-full" />
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

  const account = accounts.data?.find(
    (candidate) =>
      candidate.kind === "fiat" && candidate.currency === detail.data.currency
  )
  const availableBalance = account?.available_balance

  return (
    <AppPageFrame
      module={ROUTE_MODULE}
      title={detail.data.name}
      parents={parents}
    >
      <StokvelDetail
        stokvel={detail.data}
        availableBalance={availableBalance}
      />
    </AppPageFrame>
  )
}

function StokvelDetail({
  stokvel,
  availableBalance,
}: {
  stokvel: StokvelDetailRead
  availableBalance: string | undefined
}) {
  const cycle = stokvel.cycle
  const active = cycle?.status === "active"
  const totalRounds = active && cycle ? cycle.total_rounds : null
  // Collecting round. Stored current_round stays 0 (docs §5).
  const open = openRound(stokvel)
  const roundIndex =
    open ??
    (active && totalRounds != null && totalRounds > 0 ? totalRounds - 1 : null)
  const fillCount =
    active && totalRounds != null ? totalRounds : stokvel.member_count
  const paid = paidMemberIds(stokvel, roundIndex ?? 0)
  const outstanding = outstandingMembers(stokvel, roundIndex ?? 0)
  const currentRound =
    active && cycle && roundIndex != null
      ? cycle.rounds.find((round) => round.round === roundIndex)
      : undefined
  const estimate = stokvel.contribution_fiat_estimate
  const pool = estimate ? poolAmount(estimate, fillCount) : null
  const collected = estimate ? poolAmount(estimate, paid.size) : null
  const member = (memberId: string) =>
    stokvel.members.find((m) => m.member_id === memberId)
  const mine = myCurrentContribution(stokvel, roundIndex)
  const recipientId = currentRound?.recipient_member_id
  const recipient = recipientId ? member(recipientId) : undefined
  const recipientIsMe = recipient?.member_id === stokvel.my_member_id
  const firstName = (m: StokvelMemberRead) => (m.is_me ? "you" : firstNameOf(m))
  const plannedOrder = plannedPayoutOrder(stokvel)

  return (
    <div className="flex flex-col gap-6">
      <PageHeader>
        <div className="flex flex-wrap items-center gap-3">
          <PageHeaderTitle>{stokvel.name}</PageHeaderTitle>
          <Badge variant={active ? "default" : "outline"}>
            {active && roundIndex != null && totalRounds != null
              ? roundLabel(roundIndex, totalRounds)
              : PHASE_LABELS[stokvel.phase]}
          </Badge>
        </div>
        <PageHeaderDescription>
          {estimate && pool
            ? `${formatMoney(estimate, stokvel.currency)} per member each round · pool ${formatMoney(pool, stokvel.currency)} · `
            : "Today's exchange rate is unavailable. "}
          organised by{" "}
          {stokvel.is_organiser
            ? "you"
            : (stokvel.organiser_name ?? "the organiser")}
        </PageHeaderDescription>
      </PageHeader>

      {active && currentRound ? (
        <>
          <Card>
            <CardContent className="flex flex-col items-center gap-3">
              {pool && collected ? (
                <PotRing
                  paid={paid.size}
                  total={fillCount}
                  collected={collected}
                  pool={pool}
                  currency={stokvel.currency}
                />
              ) : null}
              <div className="flex flex-wrap justify-center gap-1.5">
                {stokvel.members.map((m) => (
                  <Badge
                    key={m.member_id}
                    variant={paid.has(m.member_id) ? "default" : "secondary"}
                  >
                    {paid.has(m.member_id)
                      ? m.is_me
                        ? "You"
                        : firstName(m)
                      : `Waiting for ${firstName(m)}`}
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>

          <ContributionPanel
            stokvel={stokvel}
            round={currentRound}
            mine={mine}
            outstanding={outstanding.length}
            availableBalance={availableBalance}
          />

          <PayoutStatus
            round={currentRound}
            totalRounds={totalRounds ?? stokvel.member_count}
            recipientName={
              recipientIsMe ? "you" : (recipient?.full_name ?? "a member")
            }
            beneficiaryName={
              recipientIsMe ? (stokvel.my_beneficiary?.full_name ?? null) : null
            }
            payoutCurrency={
              recipientIsMe
                ? (stokvel.my_beneficiary?.payout_currency ?? null)
                : null
            }
            currency={stokvel.currency}
            pool={pool}
            paid={paid.size}
            members={fillCount}
            outstandingNames={outstanding.map(firstName)}
          />
        </>
      ) : stokvel.phase === "forming" ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Setting up</CardTitle>
              <CardDescription>
                {stokvel.member_count} of {stokvel.max_members} members ·{" "}
                {pendingInvitations(stokvel).length} invited
              </CardDescription>
            </CardHeader>
          </Card>
          <PayoutBeneficiaryCard stokvel={stokvel} />
          {canInvite(stokvel) ? <InviteMemberForm stokvel={stokvel} /> : null}
          {stokvel.is_organiser ? (
            <CycleSetup stokvel={stokvel} />
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>Waiting to start</CardTitle>
                <CardDescription>
                  {stokvel.organiser_name ?? "The organiser"} starts the cycle
                  once everyone has chosen a payout beneficiary.
                </CardDescription>
              </CardHeader>
              {plannedOrder.length > 0 ? (
                <CardContent>
                  <ol className="flex flex-col gap-1">
                    {plannedOrder.map((memberId, i) => {
                      const m = member(memberId)
                      return (
                        <li key={memberId}>
                          Round {i + 1}:{" "}
                          {m?.is_me ? "You" : (m?.full_name ?? "A member")}
                        </li>
                      )
                    })}
                  </ol>
                </CardContent>
              ) : null}
            </Card>
          )}
        </>
      ) : null}

      {cycle && cycle.status !== "forming" ? (
        <PayoutQueue
          cycle={cycle}
          openRound={open}
          member={member}
          myMemberId={stokvel.my_member_id}
        />
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
              {stokvel.members.map((m) => (
                <li
                  key={m.member_id}
                  className="flex items-center justify-between gap-2 text-sm"
                >
                  <span>
                    {m.is_me ? "You" : (m.full_name ?? "A member")}
                    {m.is_organiser ? (
                      <span className="text-muted-foreground">
                        {" "}
                        · organiser
                      </span>
                    ) : null}
                  </span>
                  {active ? (
                    <Badge
                      variant={paid.has(m.member_id) ? "default" : "secondary"}
                    >
                      {paid.has(m.member_id) ? "Paid" : "Waiting"}
                    </Badge>
                  ) : null}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      {cycle && cycle.rounds.length > 0 ? (
        <RoundSchedule
          cycle={cycle}
          openRound={open}
          member={member}
          myMemberId={stokvel.my_member_id}
          paidByRound={(round) => paidMemberIds(stokvel, round).size}
          memberCount={fillCount}
        />
      ) : null}
    </div>
  )
}
