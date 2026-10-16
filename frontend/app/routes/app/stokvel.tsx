import { ArrowClockwiseIcon, UsersFourIcon } from "@phosphor-icons/react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useParams } from "react-router"

import { api } from "~/client"
import { AppPageFrame } from "~/components/app-dashboard/app-page-frame"
import { ContributionPanel } from "~/components/stokvels/contribution-panel"
import { InviteMemberForm } from "~/components/stokvels/invite-member-form"
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
  invalidateStokvels,
  myCurrentContribution,
  outstandingMembers,
  paidMemberIds,
  pendingInvitations,
  resetStokvelMockScenario,
  stokvelMockScenario,
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
 * One stokvel, the member screen (R4-05, #254): pot, your contribution and
 * the pay flow, the current round's payout, payout order, members and the
 * round history, all from `GET /stokvels/{id}` (#236, mocked for now).
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
      const status = query.state.data?.my_contribution_status
      return status === "pending" || status === "processing" ? 1500 : false
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

  // The member's fiat account in the Stokvel currency; the mock's balance
  // stands in while the API's stokvel routes do not exist.
  const account = accounts.data?.find(
    (candidate) =>
      candidate.kind === "fiat" && candidate.currency === detail.data.currency
  )
  const availableBalance = import.meta.env.DEV
    ? stokvelMockScenario.available_balance
    : account?.available_balance

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
  const paid = paidMemberIds(stokvel)
  const outstanding = outstandingMembers(stokvel)
  const currentRound = active ? cycle.rounds[cycle.current_round] : undefined
  const pool = poolAmount(
    stokvel.contribution_fiat_estimate,
    stokvel.member_count
  )
  const collected = poolAmount(stokvel.contribution_fiat_estimate, paid.size)
  const member = (memberId: string) =>
    stokvel.members.find((m) => m.member_id === memberId)
  const mine = myCurrentContribution(stokvel)
  const recipient = currentRound
    ? member(currentRound.recipient_member_id)
    : undefined
  const recipientIsMe = recipient?.member_id === stokvel.my_member_id
  const firstName = (m: { is_me: boolean; full_name: string }) =>
    m.is_me ? "you" : m.full_name.split(" ")[0]

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
        <>
          <Card>
            <CardContent className="flex flex-col items-center gap-3">
              <PotRing
                paid={paid.size}
                total={stokvel.member_count}
                collected={collected}
                pool={pool}
                currency={stokvel.currency}
              />
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
            totalRounds={cycle.total_rounds}
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
            members={stokvel.member_count}
            outstandingNames={outstanding.map(firstName)}
          />
        </>
      ) : stokvel.phase === "forming" ? (
        <Card>
          <CardHeader>
            <CardTitle>Setting up</CardTitle>
            <CardDescription>
              {stokvel.member_count} of {stokvel.max_members} members ·{" "}
              {pendingInvitations(stokvel).length} invited ·{" "}
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

      {stokvel.phase === "forming" && stokvel.is_organiser ? (
        <InviteMemberForm stokvel={stokvel} />
      ) : null}

      {cycle ? (
        <PayoutQueue
          cycle={cycle}
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
                    {m.is_me ? "You" : m.full_name}
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
          member={member}
          myMemberId={stokvel.my_member_id}
          paidByRound={(round) => paidMemberIds(stokvel, round).size}
          memberCount={stokvel.member_count}
        />
      ) : null}

      {import.meta.env.DEV ? <MockScenarios /> : null}
    </div>
  )
}

/** Development only: the states the screen must show while the API is
 * mocked (doc §6; product docx §7). Removed with the mock in R4-09. */
function MockScenarios() {
  const queryClient = useQueryClient()
  const refresh = () => invalidateStokvels(queryClient)
  return (
    <Card className="border-dashed">
      <CardHeader>
        <CardTitle>Mock scenarios</CardTitle>
        <CardDescription>
          Development only. Change the mocked API&apos;s answer, then pay.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            stokvelMockScenario.paused = !stokvelMockScenario.paused
            refresh()
          }}
        >
          {stokvelMockScenario.paused ? "Resume stokvels" : "Pause stokvels"}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            stokvelMockScenario.available_balance = "100.00"
            refresh()
          }}
        >
          Low balance
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            resetStokvelMockScenario()
            window.location.reload()
          }}
        >
          Reset
        </Button>
      </CardContent>
    </Card>
  )
}
