import { useQuery } from "@tanstack/react-query"

import { api } from "~/client"
import { QueryError } from "~/components/accounts/query-error"
import { AdminPageFrame } from "~/components/admin/admin-page-frame"
import { ForbiddenPage } from "~/components/admin/forbidden-page"
import { PlatformAccountCard } from "~/components/admin/platform-account-card"
import {
  PageHeader,
  PageHeaderDescription,
  PageHeaderTitle,
} from "~/components/ui/page-header"
import { Skeleton } from "~/components/ui/skeleton"
import { useHasPermission } from "~/hooks/use-permissions"
import { PERMISSIONS } from "~/lib/permissions"
import { adminRouteContext } from "~/routes/admin/admin.routes"
import type { Route } from "./+types/platform-accounts"

// The literal path, not `import.meta.filename` — see routes/admin/access.tsx.
const ROUTE_MODULE = "routes/admin/platform-accounts.tsx"
const pageRoutingContext = adminRouteContext(ROUTE_MODULE)

export function meta(): Route.MetaDescriptors {
  return [
    { title: `${pageRoutingContext?.title} — RemitX` },
    { name: "robots", content: "noindex" },
  ]
}

/**
 * RemitX's own balances, laid out like a customer's Accounts page. Any
 * treasurer can open it; the API refuses everyone else, and this check only
 * keeps them from a page that would fail.
 */
export default function PlatformAccounts() {
  const canRead = useHasPermission(PERMISSIONS.platformAccountRead)

  if (!canRead) return <ForbiddenPage />

  return <PlatformAccountsPage />
}

function PlatformAccountsPage() {
  const accounts = useQuery(api.admin.accounts.listPlatformAccounts())

  return (
    <AdminPageFrame module={ROUTE_MODULE}>
      <div className="flex flex-col gap-6">
        <PageHeader>
          <PageHeaderTitle>{pageRoutingContext?.title}</PageHeaderTitle>
          <PageHeaderDescription>
            RemitX&apos;s bank and fee revenue accounts in each settlement
            currency, the XRPL treasury wallet, and the RLUSD issuer.
          </PageHeaderDescription>
        </PageHeader>

        {accounts.isPending ? (
          <div className="grid gap-4 md:grid-cols-2">
            <Skeleton className="h-56" />
            <Skeleton className="h-56" />
            <Skeleton className="h-56" />
            <Skeleton className="h-56" />
          </div>
        ) : accounts.isError ? (
          <QueryError
            title="Couldn't load the platform accounts"
            error={accounts.error}
            onRetry={() => accounts.refetch()}
          />
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {accounts.data.map((account) => (
              <PlatformAccountCard key={account.account_id} account={account} />
            ))}
          </div>
        )}
      </div>
    </AdminPageFrame>
  )
}
