import { useQuery } from "@tanstack/react-query"
import { format } from "date-fns"

import { QueryError } from "~/components/accounts/query-error"
import { AdminPageFrame } from "~/components/admin/admin-page-frame"
import { StokvelFinaliseButton } from "~/components/admin/stokvel-finalise-button"
import { ChainTxHash } from "~/components/chain/tx-hash"
import { Badge } from "~/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import {
  PageHeader,
  PageHeaderDescription,
  PageHeaderTitle,
} from "~/components/ui/page-header"
import { Skeleton } from "~/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table"
import { finaliseHint, stokvelAdminQueries } from "~/lib/stokvel-admin"
import { adminRouteContext } from "~/routes/admin/admin.routes"
import type { Route } from "./+types/stokvel-rounds"

const ROUTE_MODULE = "routes/admin/stokvel-rounds.tsx"
const pageRoutingContext = adminRouteContext(ROUTE_MODULE)

export function meta(): Route.MetaDescriptors {
  return [
    { title: `${pageRoutingContext?.title} — RemitX` },
    { name: "robots", content: "noindex" },
  ]
}

/**
 * Every stokvel's current round, with a manual release for when the
 * automatic one fails (R4-11, #260; P5). List and finalise call the live API
 * (`GET /admin/stokvels/rounds`, #247).
 */
export default function StokvelRoundsPage() {
  const rounds = useQuery(stokvelAdminQueries.rounds())

  return (
    <AdminPageFrame module={ROUTE_MODULE}>
      <div className="flex flex-col gap-6">
        <PageHeader>
          <PageHeaderTitle>{pageRoutingContext?.title}</PageHeaderTitle>
          <PageHeaderDescription>
            Rounds release on their own once everyone has paid and the payout
            time has passed. Release one by hand only if that hasn&apos;t
            happened.
          </PageHeaderDescription>
        </PageHeader>

        <Card>
          <CardHeader>
            <CardTitle>Current rounds</CardTitle>
            <CardDescription>
              Each manual release is recorded in the audit log.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {rounds.isPending ? (
              <Skeleton className="h-48 w-full" />
            ) : rounds.isError ? (
              <QueryError
                title="Couldn't load the rounds"
                error={rounds.error}
                onRetry={() => rounds.refetch()}
              />
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Stokvel</TableHead>
                      <TableHead>Round</TableHead>
                      <TableHead>Paid to</TableHead>
                      <TableHead>Paid</TableHead>
                      <TableHead>Payout time</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rounds.data.length === 0 ? (
                      <TableRow>
                        <TableCell
                          colSpan={7}
                          className="text-muted-foreground"
                        >
                          No stokvel has a round in progress.
                        </TableCell>
                      </TableRow>
                    ) : (
                      rounds.data.map((round) => {
                        const hint = finaliseHint(round)
                        return (
                          <TableRow key={`${round.stokvel_id}-${round.round}`}>
                            <TableCell className="font-medium">
                              {round.stokvel_name}
                            </TableCell>
                            <TableCell>
                              {round.round + 1} of {round.total_rounds}
                            </TableCell>
                            <TableCell>{round.recipient_name}</TableCell>
                            <TableCell className="tabular-nums">
                              {round.paid_count} of {round.member_count}
                            </TableCell>
                            <TableCell className="whitespace-nowrap">
                              {format(
                                new Date(round.payout_time),
                                "EEE d MMM, HH:mm"
                              )}
                            </TableCell>
                            <TableCell>
                              {round.release_status === "released" ? (
                                <div className="flex flex-col items-start gap-1">
                                  <Badge>Released</Badge>
                                  {round.release_tx_hash ? (
                                    <ChainTxHash hash={round.release_tx_hash} />
                                  ) : null}
                                </div>
                              ) : round.release_status === "failed" ? (
                                <Badge variant="destructive">
                                  Release failed
                                </Badge>
                              ) : hint ? (
                                <span className="text-xs text-muted-foreground">
                                  {hint}
                                </span>
                              ) : (
                                <Badge variant="destructive">
                                  Ready, not released
                                </Badge>
                              )}
                            </TableCell>
                            <TableCell className="text-right">
                              <StokvelFinaliseButton round={round} />
                            </TableCell>
                          </TableRow>
                        )
                      })
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </AdminPageFrame>
  )
}
