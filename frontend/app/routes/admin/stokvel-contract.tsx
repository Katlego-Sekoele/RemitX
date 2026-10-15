import { useQuery } from "@tanstack/react-query"

import { QueryError } from "~/components/accounts/query-error"
import { AdminPageFrame } from "~/components/admin/admin-page-frame"
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
  PageHeader,
  PageHeaderDescription,
  PageHeaderTitle,
} from "~/components/ui/page-header"
import { Skeleton } from "~/components/ui/skeleton"
import { explorerAddressUrl, stokvelQueries } from "~/lib/stokvels"
import { adminRouteContext } from "~/routes/admin/admin.routes"
import type { Route } from "./+types/stokvel-contract"

const ROUTE_MODULE = "routes/admin/stokvel-contract.tsx"
const pageRoutingContext = adminRouteContext(ROUTE_MODULE)

export function meta(): Route.MetaDescriptors {
  return [
    { title: `${pageRoutingContext?.title} — RemitX` },
    { name: "robots", content: "noindex" },
  ]
}

/**
 * The stokvel contract's state (R4-02 scaffold, #251). Pause and resume are
 * R4-07 (#256) on `POST /admin/stokvel-contract/pause|unpause` (#244), and
 * the manual finalise button is R4-11 (#260). The page has no permission
 * gate yet: #244 adds the code on the API, and `lib/permissions.ts` mirrors
 * it then.
 */
export default function StokvelContractPage() {
  const contract = useQuery(stokvelQueries.contract())

  return (
    <AdminPageFrame module={ROUTE_MODULE}>
      <div className="flex flex-col gap-6">
        <PageHeader>
          <PageHeaderTitle>{pageRoutingContext?.title}</PageHeaderTitle>
          <PageHeaderDescription>
            Emergency stop for every stokvel. Pausing halts contributions and
            payouts; it never changes release conditions.
          </PageHeaderDescription>
        </PageHeader>

        {contract.isPending ? (
          <Skeleton className="h-48 w-full" />
        ) : contract.isError ? (
          <QueryError
            title="Couldn't read the contract"
            error={contract.error}
            onRetry={() => contract.refetch()}
          />
        ) : (
          <Card>
            <CardHeader>
              <div className="flex items-start justify-between gap-3">
                <CardTitle>Contract</CardTitle>
                <Badge
                  variant={contract.data.paused ? "destructive" : "outline"}
                >
                  {contract.data.paused ? "Paused" : "Running"}
                </Badge>
              </div>
              <CardDescription>{contract.data.network}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
                <dt className="text-muted-foreground">Address</dt>
                <dd className="min-w-0 truncate font-mono">
                  <a
                    href={explorerAddressUrl(contract.data.address)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {contract.data.address}
                  </a>
                </dd>
                <dt className="text-muted-foreground">Treasury balance</dt>
                <dd className="tabular-nums">
                  {contract.data.treasury_token_balance} UCTUSD
                </dd>
              </dl>
              <div className="flex flex-wrap gap-2">
                {/* Pause and resume with a required reason: #256. */}
                <Button variant="destructive" disabled>
                  {contract.data.paused
                    ? "Resume all stokvels"
                    : "Pause all stokvels"}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </AdminPageFrame>
  )
}
