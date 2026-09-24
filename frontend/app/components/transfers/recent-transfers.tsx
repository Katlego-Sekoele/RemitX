import { ArrowsLeftRightIcon } from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"

import { api } from "~/client"
import { TransfersTable } from "~/components/transfers/transfers-table"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "~/components/ui/empty"
import { Skeleton } from "~/components/ui/skeleton"
import { errorMessage } from "~/hooks/use-onboarding"

/** The caller's latest transfers, sent and received, or an empty state. */
export function RecentTransfers({ limit }: { limit?: number }) {
  const query = useQuery(
    api.remittances.listRemittances(
      limit === undefined ? undefined : { query: { limit } }
    )
  )

  if (query.isPending) return <Skeleton className="h-40 w-full" />
  if (query.isError) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Could not load your transfers</AlertTitle>
        <AlertDescription>{errorMessage(query.error)}</AlertDescription>
      </Alert>
    )
  }
  if (query.data.length === 0) {
    return (
      <Empty className="border">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <ArrowsLeftRightIcon />
          </EmptyMedia>
          <EmptyTitle>No transfers yet</EmptyTitle>
          <EmptyDescription>
            Money you send or receive shows up here.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }
  return <TransfersTable transfers={query.data} />
}
