import { useQuery } from "@tanstack/react-query"

import { api } from "~/client"
import { BeneficiaryRadar } from "~/components/dashboard/beneficiary-radar"
import { InFlightTransfers } from "~/components/dashboard/in-flight-transfers"
import { LimitHeadroom } from "~/components/dashboard/limit-headroom"
import { TransferActivityChart } from "~/components/dashboard/transfer-activity-chart"
import { QueryError } from "~/components/accounts/query-error"
import { Skeleton } from "~/components/ui/skeleton"

/** Limits, activity, who you pay, and transfers still in flight. */
export function DashboardInsights() {
  const dashboard = useQuery(api.dashboard.getDashboard())

  if (dashboard.isPending) return <Skeleton className="h-40" />
  if (dashboard.isError) {
    return (
      <QueryError
        title="Couldn't load your overview"
        error={dashboard.error}
        onRetry={() => dashboard.refetch()}
      />
    )
  }

  const { limits, activity, has_transfers, beneficiaries, in_flight } =
    dashboard.data

  return (
    <>
      <LimitHeadroom limits={limits} />
      {has_transfers ? <TransferActivityChart activity={activity} /> : null}
      {beneficiaries.length > 0 ? (
        <BeneficiaryRadar rows={beneficiaries} />
      ) : null}
      {in_flight.length > 0 ? (
        <InFlightTransfers transfers={in_flight} />
      ) : null}
    </>
  )
}
