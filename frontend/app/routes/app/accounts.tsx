import { useQuery } from "@tanstack/react-query"

import { api } from "~/client"
import { AccountCard } from "~/components/accounts/account-card"
import { AddMoneyPanel } from "~/components/accounts/add-money-panel"
import { OpenAccountButton } from "~/components/accounts/open-account-dialog"
import { QueryError } from "~/components/accounts/query-error"
import { AppPageFrame } from "~/components/app-dashboard/app-page-frame"
import { Collapsible, CollapsibleContent } from "~/components/ui/collapsible"
import {
  PageHeader,
  PageHeaderDescription,
  PageHeaderTitle,
} from "~/components/ui/page-header"
import { Skeleton } from "~/components/ui/skeleton"
import { acceptsDeposits } from "~/lib/accounts"
import { isKycVerified } from "~/lib/kyc-onboarding"
import type { Route } from "./+types/accounts"

const ROUTE_MODULE = "routes/app/accounts.tsx"

export function meta(): Route.MetaDescriptors {
  return [
    { title: "Accounts — RemitX" },
    { name: "robots", content: "noindex" },
  ]
}

export default function AccountsPage() {
  const accounts = useQuery(api.accounts.getAccounts())
  const profile = useQuery(api.me.getMyProfile())
  const zar = accounts.data?.find(acceptsDeposits)
  const heldFiat =
    accounts.data?.filter((account) => account.kind === "fiat").map(
      (account) => account.currency
    ) ?? []
  const verified = isKycVerified(profile.data?.kyc.status)

  return (
    <AppPageFrame module={ROUTE_MODULE}>
      <div className="flex flex-col gap-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <PageHeader>
            <PageHeaderTitle>Accounts</PageHeaderTitle>
            <PageHeaderDescription>
              Your balances, and the reference that identifies each account.
            </PageHeaderDescription>
          </PageHeader>
          <div className="flex max-w-sm flex-col items-end gap-2">
            <OpenAccountButton verified={verified} heldCurrencies={heldFiat} />
          </div>
        </div>

        {accounts.isPending ? (
          <div className="grid gap-4 md:grid-cols-2">
            <Skeleton className="h-64" />
            <Skeleton className="h-64" />
          </div>
        ) : accounts.isError ? (
          <QueryError
            title="Couldn't load your accounts"
            error={accounts.error}
            onRetry={() => accounts.refetch()}
          />
        ) : (
          // Add money is an inline panel, not a modal: its details are read
          // while paying from a banking app, and nothing in it is final.
          <Collapsible className="flex flex-col gap-4">
            <div className="grid gap-4 md:grid-cols-2">
              {accounts.data.map((account) => (
                <AccountCard key={account.account_id} account={account} />
              ))}
            </div>
            {zar ? (
              <CollapsibleContent>
                <AddMoneyPanel reference={zar.reference} />
              </CollapsibleContent>
            ) : null}
          </Collapsible>
        )}
      </div>
    </AppPageFrame>
  )
}
