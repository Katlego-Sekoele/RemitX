import { ArrowClockwiseIcon, UsersFourIcon } from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router"

import { AppPageFrame } from "~/components/app-dashboard/app-page-frame"
import { ContributionAtTodaysRate } from "~/components/stokvels/contribution-at-rate"
import { InvitationCard } from "~/components/stokvels/invitation-card"
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
import {
  stokvelNewPath,
  stokvelPath,
  stokvelQueries,
  type StokvelRead,
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
 * The member's stokvels and pending invitations (R4-02, #251), from
 * `GET /stokvels` (#229). The create wizard is at app/stokvels/new (#252);
 * invitations are accepted or declined here (#253). Round and payout
 * details live on each stokvel's own page.
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
          <Button nativeButton={false} render={<Link to={stokvelNewPath()} />}>
            New stokvel
          </Button>
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
              <Button
                nativeButton={false}
                render={<Link to={stokvelNewPath()} />}
              >
                Start a stokvel
              </Button>
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

function StokvelCard({ stokvel }: { stokvel: StokvelRead }) {
  const closed = stokvel.deactivated_at !== null
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <CardTitle>
            <Link to={stokvelPath(stokvel.stokvel_id)}>{stokvel.name}</Link>
          </CardTitle>
          {closed ? (
            <Badge variant="outline">Closed</Badge>
          ) : stokvel.is_organiser ? (
            <Badge variant="secondary">You organise</Badge>
          ) : null}
        </div>
        <CardDescription>
          <ContributionAtTodaysRate
            amount={stokvel.contribution_amount}
            currency={stokvel.currency}
          />{" "}
          per member, per round
        </CardDescription>
      </CardHeader>
      <CardContent className="flex items-center justify-between gap-3">
        <span className="text-sm text-muted-foreground">
          {stokvel.member_count} of {stokvel.max_members} members
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

export function StokvelListSkeleton() {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {Array.from({ length: 3 }, (_, i) => (
        <Skeleton key={i} className="h-32 w-full" />
      ))}
    </div>
  )
}
