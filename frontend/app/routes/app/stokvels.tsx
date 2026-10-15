import { ArrowClockwiseIcon, UsersFourIcon } from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"
import { format } from "date-fns"
import { Link } from "react-router"

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
  PHASE_LABELS,
  roundLabel,
  stokvelPath,
  stokvelQueries,
  type StokvelInvitationRead,
  type StokvelSummaryRead,
} from "~/lib/stokvels"
import type { Route } from "./+types/stokvels"

const ROUTE_MODULE = "routes/app/stokvels.tsx"

export function meta(): Route.MetaDescriptors {
  return [
    { title: "Stokvels — RemitX" },
    { name: "robots", content: "noindex" },
  ]
}

/**
 * The member's stokvels and pending invitations (R4-02 scaffold, #251).
 * Reads mocked data until the API lands; the create form is R4-03 (#252),
 * invitation actions are R4-04 (#253).
 */
export default function StokvelsPage() {
  const list = useQuery(stokvelQueries.list())

  return (
    <AppPageFrame module={ROUTE_MODULE}>
      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <PageHeader>
            <PageHeaderTitle>Stokvels</PageHeaderTitle>
            <PageHeaderDescription>
              Save together, pay out in turn.
            </PageHeaderDescription>
          </PageHeader>
          {/* The create wizard arrives in #252. */}
          <Button disabled>New stokvel</Button>
        </div>

        {list.isPending ? (
          <StokvelListSkeleton />
        ) : list.isError ? (
          <Alert variant="destructive">
            <AlertTitle>Couldn&apos;t load your stokvels</AlertTitle>
            <AlertDescription>{errorMessage(list.error)}</AlertDescription>
            <AlertAction>
              <Button
                variant="outline"
                size="sm"
                disabled={list.isFetching}
                onClick={() => list.refetch()}
              >
                <ArrowClockwiseIcon data-icon="inline-start" />
                Retry
              </Button>
            </AlertAction>
          </Alert>
        ) : list.data.stokvels.length === 0 &&
          list.data.invitations.length === 0 ? (
          <Empty className="border">
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <UsersFourIcon />
              </EmptyMedia>
              <EmptyTitle>No stokvels yet</EmptyTitle>
              <EmptyDescription>
                Start one and invite people you trust, or wait for an
                invitation.
              </EmptyDescription>
            </EmptyHeader>
            <EmptyContent>
              <Button disabled>Start a stokvel</Button>
            </EmptyContent>
          </Empty>
        ) : (
          <>
            {list.data.invitations.length > 0 ? (
              <section className="flex flex-col gap-3">
                <h2 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                  Invitations
                </h2>
                {list.data.invitations.map((invitation) => (
                  <InvitationCard
                    key={invitation.invitation_id}
                    invitation={invitation}
                  />
                ))}
              </section>
            ) : null}
            <section className="flex flex-col gap-3">
              <h2 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                Your stokvels
              </h2>
              <div className="grid gap-3 md:grid-cols-2">
                {list.data.stokvels.map((stokvel) => (
                  <StokvelCard key={stokvel.stokvel_id} stokvel={stokvel} />
                ))}
              </div>
            </section>
          </>
        )}
      </div>
    </AppPageFrame>
  )
}

function StokvelCard({ stokvel }: { stokvel: StokvelSummaryRead }) {
  const active =
    stokvel.phase === "active" &&
    stokvel.current_round !== null &&
    stokvel.total_rounds !== null
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <CardTitle>
            <Link to={stokvelPath(stokvel.stokvel_id)}>{stokvel.name}</Link>
          </CardTitle>
          <Badge variant={stokvel.phase === "active" ? "default" : "outline"}>
            {active
              ? roundLabel(stokvel.current_round!, stokvel.total_rounds!)
              : PHASE_LABELS[stokvel.phase]}
          </Badge>
        </div>
        <CardDescription>
          {formatMoney(stokvel.contribution_fiat_estimate, stokvel.currency)}{" "}
          per member · {stokvel.member_count} members ·{" "}
          {stokvel.is_organiser ? "you organise" : stokvel.organiser_name}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex items-center justify-between gap-3">
        <span className="text-sm text-muted-foreground">
          {stokvel.next_payout_time
            ? `Payout ${format(new Date(stokvel.next_payout_time), "EEE d MMM")}`
            : stokvel.phase === "forming"
              ? "No cycle started yet"
              : "No upcoming payout"}
        </span>
        <Button
          variant="outline"
          size="sm"
          nativeButton={false}
          render={<Link to={stokvelPath(stokvel.stokvel_id)} />}
        >
          Open
        </Button>
      </CardContent>
    </Card>
  )
}

function InvitationCard({ invitation }: { invitation: StokvelInvitationRead }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <CardTitle>{invitation.stokvel_name}</CardTitle>
          <Badge variant="secondary">Invitation</Badge>
        </div>
        <CardDescription>
          {invitation.organiser_name} invited you ·{" "}
          {formatMoney(
            invitation.contribution_fiat_estimate,
            invitation.currency
          )}{" "}
          per round · {invitation.member_count} members
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center gap-2">
        {/* Accept and decline arrive in #253. */}
        <Button size="sm" disabled>
          Accept
        </Button>
        <Button size="sm" variant="ghost" disabled>
          Decline
        </Button>
        <span className="text-xs text-muted-foreground">
          Invitations lapse when the organiser starts the cycle.
        </span>
      </CardContent>
    </Card>
  )
}

export function StokvelListSkeleton() {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {Array.from({ length: 3 }, (_, i) => (
        <Skeleton key={i} className="h-32 w-full" />
      ))}
    </div>
  )
}
