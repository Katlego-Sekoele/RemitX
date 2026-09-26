import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router"

import { api } from "~/client"
import { QueryError } from "~/components/accounts/query-error"
import { ShareRadial } from "~/components/dashboard/share-radial"
import { Button } from "~/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import {
  DescriptionDetails,
  DescriptionItem,
  DescriptionList,
  DescriptionTerm,
} from "~/components/ui/description-list"
import { Skeleton } from "~/components/ui/skeleton"
import { useHasPermission } from "~/hooks/use-permissions"
import { usedShare } from "~/lib/chart-series"
import {
  formatMoney,
  isZeroMoney,
  SETTLEMENT_TOKEN_LABEL,
} from "~/lib/money"
import { PERMISSIONS } from "~/lib/permissions"

/** Treasury token still available, against token customers already hold. */
export function TreasuryCoverage() {
  const canRead = useHasPermission(PERMISSIONS.platformAccountRead)
  const coverage = useQuery({
    ...api.admin.accounts.getTreasuryCoverage(),
    enabled: canRead,
  })

  if (!canRead) return null
  if (coverage.isPending) return <Skeleton className="h-40" />
  if (coverage.isError) {
    return (
      <QueryError
        title="Couldn't load treasury coverage"
        error={coverage.error}
        onRetry={() => coverage.refetch()}
      />
    )
  }

  const available = coverage.data.token_available
  const owed = coverage.data.customer_token_balances
  const share = isZeroMoney(owed) ? 1 : usedShare(available, owed)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Treasury coverage</CardTitle>
        <CardDescription>
          {SETTLEMENT_TOKEN_LABEL} the house wallet can still spend, against
          what customers hold.
        </CardDescription>
        <CardAction>
          <Button
            variant="link"
            nativeButton={false}
            render={<Link to="/admin/platform-accounts" />}
          >
            Platform accounts
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col items-center gap-6 sm:flex-row sm:items-center">
        <ShareRadial share={share} label={`${Math.round(share * 100)}%`} />
        <DescriptionList>
          <DescriptionItem>
            <DescriptionTerm>Available</DescriptionTerm>
            <DescriptionDetails className="font-heading text-2xl font-semibold tabular-nums">
              {formatMoney(available, "", "settlement")}
            </DescriptionDetails>
          </DescriptionItem>
          <DescriptionItem>
            <DescriptionTerm>Customer balances</DescriptionTerm>
            <DescriptionDetails className="font-heading text-2xl font-semibold tabular-nums">
              {formatMoney(owed, "", "settlement")}
            </DescriptionDetails>
          </DescriptionItem>
        </DescriptionList>
      </CardContent>
    </Card>
  )
}
