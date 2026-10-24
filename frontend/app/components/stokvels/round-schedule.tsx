import { ArrowSquareOutIcon } from "@phosphor-icons/react"
import { format } from "date-fns"

import { Avatar, AvatarFallback } from "~/components/ui/avatar"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
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

/** Member avatars in payout order; the current round's recipient is marked
 * and, when it is the viewer, says "You're next!" (product docx §3). */
export function PayoutQueue({
  cycle,
  member,
  myMemberId,
}: {
  cycle: StokvelDetailCycleRead
  member: MemberLookup
  myMemberId: string
}) {
  const active = cycle.status === "active"
  return (
    <Card>
      <CardHeader>
        <CardTitle>Payout order</CardTitle>
        <CardDescription>
          {cycle.rounds.filter((r) => r.release_status === "released").length}{" "}
          of {cycle.total_rounds ?? cycle.payout_order.length} paid out
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ol className="flex gap-2 overflow-x-auto pb-1">
          {cycle.payout_order.map((memberId, round) => {
            const m = member(memberId)
            const name = m?.full_name ?? "Member"
            const isMe = memberId === myMemberId
            const isNext =
              active &&
              cycle.current_round != null &&
              round === cycle.current_round
            const released = cycle.rounds[round]?.release_status === "released"
            return (
              <li
                key={memberId}
                className="flex min-w-24 flex-1 flex-col items-center gap-1 text-center"
              >
                <Avatar
                  className={
                    isNext
                      ? "size-10 ring-2 ring-primary ring-offset-2"
                      : "size-10"
                  }
                >
                  <AvatarFallback>
                    {beneficiaryInitials({ full_name: name })}
                  </AvatarFallback>
                </Avatar>
                <span className="text-sm font-medium">
                  {isMe ? "You" : name.split(" ")[0]}
                </span>
                <span className="text-xs text-muted-foreground">
                  Round {round + 1}
                  {cycle.rounds[round]
                    ? ` · ${format(new Date(cycle.rounds[round].payout_time), "d MMM")}`
                    : ""}
                </span>
                {released ? (
                  <Badge variant="outline">Paid out</Badge>
                ) : isNext ? (
                  <Badge>{isMe ? "You're next!" : "Next"}</Badge>
                ) : null}
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
  member,
  myMemberId,
  paidByRound,
  memberCount,
}: {
  cycle: StokvelDetailCycleRead
  member: MemberLookup
  myMemberId: string
  /** Confirmed contributions per round index. */
  paidByRound: (round: number) => number
  memberCount: number
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Rounds</CardTitle>
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
            const current = cycle.current_round
            const isCurrent =
              cycle.status === "active" &&
              current != null &&
              round.round === current
            const upcoming =
              cycle.status === "active" &&
              current != null &&
              round.round > current
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
