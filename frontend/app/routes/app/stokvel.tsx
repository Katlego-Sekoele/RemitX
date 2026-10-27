import { ArrowClockwiseIcon, UsersFourIcon } from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"
import { useEffect, useRef } from "react"
import { Link, useParams } from "react-router"
import { toast } from "sonner"

import { api } from "~/client"
import { AppPageFrame } from "~/components/app-dashboard/app-page-frame"
import { ContinueOrLeaveCard } from "~/components/stokvels/continue-or-leave-card"
import { ContributionPanel } from "~/components/stokvels/contribution-panel"
import { PayoutBeneficiaryCard } from "~/components/stokvels/payout-beneficiary-card"
import { RosterReadout } from "~/components/stokvels/payout-order-list"
import { PayoutStatus } from "~/components/stokvels/payout-status"
import { SetupWizard } from "~/components/stokvels/setup-wizard"
import { PotRing } from "~/components/stokvels/pot-ring"
import { StokvelCoverBanner } from "~/components/stokvels/stokvel-cover"
import { StokvelInvitations } from "~/components/stokvels/stokvel-invitations"
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
import { PageHeader, PageHeaderDescription } from "~/components/ui/page-header"
import { Skeleton } from "~/components/ui/skeleton"
import { errorMessage } from "~/hooks/use-onboarding"
import { formatMoney } from "~/lib/money"
import {
  arrangeRoster,
  cycleRoster,
  savedRosterOrder,
} from "~/lib/stokvel-setup"
import {
  continuationStatus,
  firstNameOf,
  myCurrentContribution,
  outstandingMembers,
  paidMemberIds,
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
 * The organiser's setup is a stepper (people, order, schedule, start).
 */
export default function StokvelPage() {
  const { stokvelId = "" } = useParams()
  const detail = useQuery({
    ...stokvelQueries.detail(stokvelId),
    enabled: Boolean(stokvelId),
  })
  const accounts = useQuery(api.accounts.getAccounts())

  const parents = [{ label: "Stokvels", href: stokvelsPath() }]

  // A later poll can fail while the last read is still on screen. Keep it.
  if (detail.data == null) {
    if (!detail.isError) {
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
  const previous = stokvel.previous_cycle
  const continuation = continuationStatus(stokvel)
  const active = cycle?.status === "active"
  const totalRounds = active && cycle ? cycle.total_rounds : null
  // Collecting round from the detail response. Stored current_round stays 0.
  const open = stokvel.open_round
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
  const formingRoster = arrangeRoster(
    cycleRoster(stokvel),
    savedRosterOrder(stokvel),
    null
  )
  const showAside =
    Boolean(active && currentRound) ||
    (stokvel.phase === "forming" && stokvel.invitations.length > 0)

  return (
    <div className="flex flex-col gap-6">
      <StokvelCoverBanner
        name={stokvel.name}
        coverUrl={stokvel.cover_url}
        stokvelId={stokvel.stokvel_id}
        canEdit={stokvel.deactivated_at == null}
        badge={
          <Badge variant={active ? "default" : "outline"}>
            {active && roundIndex != null && totalRounds != null
              ? roundLabel(roundIndex, totalRounds)
              : PHASE_LABELS[stokvel.phase]}
          </Badge>
        }
      />
      <PageHeader>
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

      <CycleOpeningToast stokvel={stokvel} />

      {stokvel.phase === "forming" && stokvel.is_organiser ? (
        <>
          <SetupWizard stokvel={stokvel} />
          {previous ? (
            <RoundSchedule
              cycle={previous}
              openRound={null}
              member={member}
              myMemberId={stokvel.my_member_id}
              paidByRound={() => previous.rounds.length}
              memberCount={previous.rounds.length}
              title={`Cycle ${previous.cycle_number}`}
            />
          ) : null}
        </>
      ) : (
        <div
          className={
            showAside
              ? "grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_20rem] xl:grid-cols-[minmax(0,1fr)_22rem]"
              : "grid items-start gap-4"
          }
        >
          {showAside ? (
            <aside className="flex flex-col gap-4 lg:sticky lg:top-4 lg:order-last">
              {active && currentRound ? (
                <PayoutStatus
                  round={currentRound}
                  totalRounds={totalRounds ?? stokvel.member_count}
                  recipientName={
                    recipientIsMe ? "you" : (recipient?.full_name ?? "a member")
                  }
                  beneficiaryName={
                    recipientIsMe
                      ? (stokvel.my_beneficiary?.full_name ?? null)
                      : null
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
              ) : null}
              {stokvel.phase === "forming" ? (
                <StokvelInvitations stokvel={stokvel} />
              ) : null}
            </aside>
          ) : null}

          <div className="flex min-w-0 flex-col gap-4">
            {active && currentRound ? (
              pool && collected ? (
                <Card className="sm:flex-row sm:items-center">
                  <div className="flex shrink-0 justify-center px-(--card-spacing) sm:pr-0">
                    <PotRing
                      paid={paid.size}
                      total={fillCount}
                      collected={collected}
                      pool={pool}
                      currency={stokvel.currency}
                    />
                  </div>
                  <ContributionPanel
                    bare
                    stokvel={stokvel}
                    round={currentRound}
                    mine={mine}
                    outstanding={outstanding.length}
                    availableBalance={availableBalance}
                  />
                </Card>
              ) : (
                <ContributionPanel
                  stokvel={stokvel}
                  round={currentRound}
                  mine={mine}
                  outstanding={outstanding.length}
                  availableBalance={availableBalance}
                />
              )
            ) : null}

            {stokvel.phase === "forming" ? (
              <>
                <ContinueOrLeaveCard stokvel={stokvel} />
                {/* Choosing a payout beneficiary for the next cycle counts as
                    continuing (#237), so an undecided member chooses on the
                    card above instead. */}
                {continuation !== "undecided" ? (
                  <PayoutBeneficiaryCard stokvel={stokvel} />
                ) : null}
                <Card>
                  <CardHeader>
                    <CardTitle>Waiting to start</CardTitle>
                    <CardDescription>
                      {stokvel.organiser_name ?? "The organiser"} starts the
                      cycle once everyone invited has joined.
                    </CardDescription>
                  </CardHeader>
                  {formingRoster.length > 0 ? (
                    <CardContent>
                      <RosterReadout roster={formingRoster} />
                    </CardContent>
                  ) : null}
                </Card>
              </>
            ) : null}

            {cycle && cycle.status !== "forming" ? (
              <PayoutQueue
                cycle={cycle}
                openRound={open}
                member={member}
                myMemberId={stokvel.my_member_id}
                paidIds={paid}
              />
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

            {previous ? (
              <RoundSchedule
                cycle={previous}
                openRound={null}
                member={member}
                myMemberId={stokvel.my_member_id}
                paidByRound={() => previous.rounds.length}
                memberCount={previous.rounds.length}
                title={`Cycle ${previous.cycle_number}`}
              />
            ) : null}
          </div>
        </div>
      )}
    </div>
  )
}

/** The cycle is active in the database before `startCycle` is mined. */
function CycleOpeningToast({ stokvel }: { stokvel: StokvelDetailRead }) {
  const opening =
    stokvel.cycle?.status === "active" && stokvel.cycle.registered_at == null
  const wasOpening = useRef(false)
  const toastId = `cycle-open-${stokvel.stokvel_id}`

  useEffect(() => {
    if (opening) {
      wasOpening.current = true
      toast.loading("Opening the cycle on the network…", { id: toastId })
      return
    }
    if (wasOpening.current && stokvel.cycle?.registered_at) {
      wasOpening.current = false
      toast.success("The cycle is open", { id: toastId })
    }
  }, [opening, stokvel.cycle?.registered_at, toastId])

  return null
}
