import { ArrowSquareOutIcon } from "@phosphor-icons/react"
import { format } from "date-fns"

import { Avatar, AvatarFallback } from "~/components/ui/avatar"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemMedia,
  ItemTitle,
} from "~/components/ui/item"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import { beneficiaryInitials } from "~/lib/beneficiaries"
import {
  explorerTxUrl,
  payoutProofHash,
  PAYOUT_STAGE_LABELS,
  payoutStage,
  type StokvelDetailCycleRead,
  type StokvelMemberRead,
} from "~/lib/stokvels"

type MemberLookup = (memberId: string) => StokvelMemberRead | undefined

/** Payout order and who still owes the open round, on one card. The pot
 * already shows how much of this round is in. */
export function PayoutQueue({
  cycle,
  openRound,
  member,
  myMemberId,
  paidIds,
}: {
  cycle: StokvelDetailCycleRead
  /** Collecting round. Null when none is open, including a finished cycle. */
  openRound: number | null
  member: MemberLookup
  myMemberId: string
  /** Members who have paid the open round. */
  paidIds: ReadonlySet<string>
}) {
  const releasedCount = cycle.rounds.filter(
    (round) => round.release_status === "released"
  ).length
  const total = cycle.total_rounds ?? cycle.payout_order.length
  const waiting =
    openRound == null
      ? []
      : cycle.payout_order.filter((memberId) => !paidIds.has(memberId))

  return (
    <Card>
      <CardHeader>
        <CardTitle>Payout order</CardTitle>
        <CardDescription>
          {releasedCount} of {total} paid out
          {openRound != null
            ? waiting.length === 0
              ? " · everyone has paid this round"
              : ` · still to pay: ${waiting
                  .map((memberId) => {
                    const person = member(memberId)
                    return memberId === myMemberId
                      ? "you"
                      : (person?.full_name?.split(" ")[0] ?? "a member")
                  })
                  .join(", ")}`
            : ""}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ol className="flex flex-col gap-2">
          {cycle.payout_order.map((memberId, round) => {
            const person = member(memberId)
            const name = person?.full_name ?? "Member"
            const isMe = memberId === myMemberId
            const isOpen = openRound != null && round === openRound
            const released = cycle.rounds[round]?.release_status === "released"
            const paid = paidIds.has(memberId)
            const when = cycle.rounds[round]
              ? format(new Date(cycle.rounds[round].payout_time), "d MMM")
              : null
            return (
              <li key={memberId}>
                <Item variant="outline">
                  <ItemMedia>
                    <Avatar>
                      <AvatarFallback>
                        {beneficiaryInitials({ full_name: name })}
                      </AvatarFallback>
                    </Avatar>
                  </ItemMedia>
                  <ItemContent>
                    <ItemTitle>
                      {isMe ? "You" : name}
                      {person?.is_organiser ? " · organiser" : ""}
                    </ItemTitle>
                    <ItemDescription>
                      Round {round + 1}
                      {when ? ` · ${when}` : ""}
                    </ItemDescription>
                  </ItemContent>
                  <ItemActions>
                    {openRound != null && !released ? (
                      <Badge variant={paid ? "default" : "secondary"}>
                        {paid ? "Paid" : "Waiting"}
                      </Badge>
                    ) : null}
                    {released ? (
                      <Badge variant="outline">Paid out</Badge>
                    ) : isOpen ? (
                      <Badge>{isMe ? "You're next!" : "Next"}</Badge>
                    ) : (
                      <Badge variant="outline">Upcoming</Badge>
                    )}
                  </ItemActions>
                </Item>
              </li>
            )
          })}
        </ol>
      </CardContent>
    </Card>
  )
}

/** Every round of the cycle with who it pays, when, and how far it got. */
export function RoundSchedule({
  cycle,
  openRound,
  member,
  myMemberId,
  paidByRound,
  memberCount,
  title = "Rounds",
}: {
  cycle: StokvelDetailCycleRead
  /** Collecting round. Null when none is open, including a finished cycle. */
  openRound: number | null
  member: MemberLookup
  myMemberId: string
  /** Confirmed contributions per round index. */
  paidByRound: (round: number) => number
  memberCount: number
  title?: string
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col divide-y">
          {cycle.rounds.map((round) => {
            const recipient = round.recipient_member_id
              ? member(round.recipient_member_id)
              : undefined
            const name =
              round.recipient_member_id === myMemberId
                ? "you"
                : (recipient?.full_name ?? "a member")
            const isCurrent = openRound != null && round.round === openRound
            const upcoming = openRound != null && round.round > openRound
            const paid = paidByRound(round.round)
            const stage = payoutStage(round, paid >= memberCount)
            const proof = payoutProofHash(round)
            return (
              <li
                key={round.round}
                className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm"
              >
                <div className="flex flex-col">
                  <span className="font-medium">
                    Round {round.round + 1} · paid to {name}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {upcoming
                      ? `Opens ${format(new Date(round.start_time), "EEE d MMM")} · payout ${format(new Date(round.payout_time), "EEE d MMM")}`
                      : isCurrent
                        ? `${paid} of ${memberCount} paid · releases ${format(new Date(round.payout_time), "EEE d MMM, HH:mm")}`
                        : `Released ${format(new Date(round.payout_time), "EEE d MMM")}`}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  {upcoming ? (
                    <Badge variant="outline">Upcoming</Badge>
                  ) : isCurrent && stage === "collecting" ? (
                    <Badge variant="secondary">
                      {paid >= memberCount
                        ? "Open"
                        : `Waiting for ${memberCount - paid}`}
                    </Badge>
                  ) : (
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
                  )}
                  {proof ? (
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
                      Proof
                      <ArrowSquareOutIcon
                        data-icon="inline-end"
                        aria-hidden="true"
                      />
                    </Button>
                  ) : null}
                </div>
              </li>
            )
          })}
        </ul>
      </CardContent>
    </Card>
  )
}
