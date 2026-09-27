import { ArrowsClockwiseIcon } from "@phosphor-icons/react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { Link } from "react-router"
import { toast } from "sonner"

import { api, TransactionStatus, type StuckSettlementRead } from "~/client"
import { CopyButton } from "~/components/accounts/copy-button"
import { QueryError } from "~/components/accounts/query-error"
import { AdminPageFrame } from "~/components/admin/admin-page-frame"
import { ForbiddenPage } from "~/components/admin/forbidden-page"
import { formatDateTime } from "~/components/admin/kyc-review/format"
import { XrplHash } from "~/components/transfers/xrpl-hash"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "~/components/ui/alert-dialog"
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
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "~/components/ui/empty"
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
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "~/components/ui/tooltip"
import { errorMessage } from "~/hooks/use-onboarding"
import { useHasPermission } from "~/hooks/use-permissions"
import { PERMISSIONS } from "~/lib/permissions"
import { canRetryEnqueue, recoveryKindCopy } from "~/lib/settlement-recovery"
import { statusCopy, transferPath } from "~/lib/transfers"
import { adminRouteContext } from "~/routes/admin/admin.routes"
import type { Route } from "./+types/stuck-settlements"

const ROUTE_MODULE = "routes/admin/stuck-settlements.tsx"
const pageRoutingContext = adminRouteContext(ROUTE_MODULE)

const stuckQuery = () => api.admin.operations.listStuckSettlements()

export function meta(): Route.MetaDescriptors {
  return [
    { title: `${pageRoutingContext?.title} — RemitX` },
    { name: "robots", content: "noindex" },
  ]
}

/**
 * List: ``transaction:read_any`` (routes/admin/operations.py). Retry and bulk
 * reclaim: ``settlement:retry`` on top.
 */
export default function StuckSettlements() {
  const canRead = useHasPermission(PERMISSIONS.transactionReadAny)

  if (!canRead) return <ForbiddenPage />

  return <StuckSettlementsPage />
}

function StuckSettlementsPage() {
  const queryClient = useQueryClient()
  const canRetry = useHasPermission(PERMISSIONS.settlementRetry)
  const stuck = useQuery(stuckQuery())

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: stuckQuery().queryKey })

  const reclaim = useMutation({
    ...api.admin.operations.reclaimPendingSettlements(),
    onSuccess: (data) => {
      const count = data.requeued_quote_ids.length
      toast.success(
        count === 0
          ? "No fully pending groups were re-enqueued"
          : `Re-enqueued ${count} settlement${count === 1 ? "" : "s"}`
      )
      refresh()
    },
    onError: (error) => {
      toast.error(errorMessage(error))
    },
  })

  const retryableCount =
    stuck.data?.filter((row) => canRetryEnqueue(row.recovery_kind)).length ?? 0

  return (
    <AdminPageFrame module={ROUTE_MODULE}>
      <div className="flex flex-col gap-6">
        <PageHeader>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex flex-col gap-2">
              <PageHeaderTitle>{pageRoutingContext?.title}</PageHeaderTitle>
              <PageHeaderDescription>
                Remittances whose settlement leg is not confirmed. Re-enqueue
                only when every leg is still pending; processing or failed
                groups need manual investigation on XRPL.
              </PageHeaderDescription>
            </div>
            {canRetry ? (
              <AlertDialog>
                <AlertDialogTrigger
                  render={
                    <Button
                      variant="outline"
                      disabled={
                        stuck.isPending ||
                        reclaim.isPending ||
                        retryableCount === 0
                      }
                    />
                  }
                >
                  <ArrowsClockwiseIcon data-icon="inline-start" />
                  Reclaim all pending
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>
                      Re-enqueue all safe settlements?
                    </AlertDialogTitle>
                    <AlertDialogDescription>
                      This runs the same reclaim as the worker: only groups
                      where every leg is still pending are published again (
                      {retryableCount} ready now). Groups that are processing or
                      failed are skipped.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      disabled={reclaim.isPending}
                      onClick={() =>
                        reclaim.mutate({ body: { min_age_seconds: 0 } })
                      }
                    >
                      Reclaim now
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            ) : null}
          </div>
        </PageHeader>

        <Card>
          <CardHeader>
            <CardTitle>Non-terminal settlements</CardTitle>
            <CardDescription>
              Oldest first. Use retry enqueue for a single quote, or reclaim all
              pending when several transfers are stuck off the queue.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {stuck.isPending ? (
              <Skeleton className="h-48 w-full" />
            ) : stuck.isError ? (
              <QueryError
                title="Couldn't load stuck settlements"
                error={stuck.error}
                onRetry={() => stuck.refetch()}
              />
            ) : stuck.data.length === 0 ? (
              <Empty>
                <EmptyHeader>
                  <EmptyTitle>Nothing stuck</EmptyTitle>
                  <EmptyDescription>
                    Confirmed transfers drop off this list. Failed or processing
                    groups appear here until resolved.
                  </EmptyDescription>
                </EmptyHeader>
              </Empty>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Created</TableHead>
                    <TableHead>Quote</TableHead>
                    <TableHead>Transfer</TableHead>
                    <TableHead>Leg status</TableHead>
                    <TableHead className="text-right">Legs</TableHead>
                    <TableHead>Recovery</TableHead>
                    <TableHead>Burn hash</TableHead>
                    {canRetry ? (
                      <TableHead className="text-right">Actions</TableHead>
                    ) : null}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {stuck.data.map((row) => (
                    <StuckSettlementRow
                      key={row.quote_id}
                      row={row}
                      canRetry={canRetry}
                      onRetried={refresh}
                    />
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </AdminPageFrame>
  )
}

function StuckSettlementRow({
  row,
  canRetry,
  onRetried,
}: {
  row: StuckSettlementRead
  canRetry: boolean
  onRetried: () => void
}) {
  const [retrying, setRetrying] = useState(false)
  const recovery = recoveryKindCopy(row.recovery_kind)
  const legStatus = (Object.values(TransactionStatus) as string[]).includes(
    row.settlement_leg_status
  )
    ? (row.settlement_leg_status as TransactionStatus)
    : TransactionStatus.PENDING
  const leg = statusCopy(legStatus)
  const retryAllowed = canRetry && canRetryEnqueue(row.recovery_kind)

  const retry = useMutation({
    ...api.admin.operations.retrySettlementEnqueue(),
    onSuccess: () => {
      toast.success("Settlement job re-enqueued")
      onRetried()
    },
    onError: (error) => {
      toast.error(errorMessage(error))
    },
    onSettled: () => setRetrying(false),
  })

  function handleRetry() {
    setRetrying(true)
    retry.mutate({ path: { quote_id: row.quote_id } })
  }

  const legSummary = `P ${row.pending_leg_count} · Proc ${row.processing_leg_count} · F ${row.failed_leg_count}`

  return (
    <TableRow>
      <TableCell className="whitespace-nowrap">
        {formatDateTime(row.created_at)}
      </TableCell>
      <TableCell>
        <span className="inline-flex items-center gap-1 font-mono text-xs">
          <span className="max-w-[8rem] truncate" title={row.quote_id}>
            {row.quote_id}
          </span>
          <CopyButton value={row.quote_id} label="Quote ID" />
        </span>
      </TableCell>
      <TableCell>
        <Button
          variant="link"
          size="sm"
          nativeButton={false}
          render={<Link to={transferPath(row.remittance_id)} />}
        >
          View transfer
        </Button>
      </TableCell>
      <TableCell>
        <Badge variant={leg.badge}>{leg.label}</Badge>
      </TableCell>
      <TableCell className="text-right font-mono text-xs tabular-nums">
        {legSummary}
      </TableCell>
      <TableCell>
        <Tooltip>
          <TooltipTrigger
            render={
              <Badge variant={recovery.badge} className="cursor-default" />
            }
          >
            {recovery.label}
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-xs text-pretty">
            {recovery.retryHint}
          </TooltipContent>
        </Tooltip>
      </TableCell>
      <TableCell>
        {row.burn_xrpl_tx_hash ? (
          <XrplHash hash={row.burn_xrpl_tx_hash} />
        ) : (
          "—"
        )}
      </TableCell>
      {canRetry ? (
        <TableCell className="text-right">
          {retryAllowed ? (
            <Button
              size="sm"
              variant="outline"
              disabled={retrying || retry.isPending}
              onClick={handleRetry}
            >
              Retry enqueue
            </Button>
          ) : (
            <Tooltip>
              <TooltipTrigger
                render={
                  <Button
                    size="sm"
                    variant="outline"
                    disabled
                    className="pointer-events-auto"
                  />
                }
              >
                Retry enqueue
              </TooltipTrigger>
              <TooltipContent side="top" className="max-w-xs text-pretty">
                {recovery.retryHint}
              </TooltipContent>
            </Tooltip>
          )}
        </TableCell>
      ) : null}
    </TableRow>
  )
}
