import { ArrowCircleUpIcon, BankIcon } from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"
import { Link, useSearchParams } from "react-router"

import { api } from "~/client"
import { QueryError } from "~/components/accounts/query-error"
import { AppPageFrame } from "~/components/app-dashboard/app-page-frame"
import { Button } from "~/components/ui/button"
import {
  Empty,
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
import { WithdrawForm } from "~/components/withdrawals/withdraw-form"
import { WithdrawalsTable } from "~/components/withdrawals/withdrawals-table"
import { BANK_ACCOUNTS_HREF, canWithdrawFrom } from "~/lib/withdrawals"
import type { Route } from "./+types/withdraw"

const ROUTE_MODULE = "routes/app/withdraw.tsx"

export function meta(): Route.MetaDescriptors {
  return [
    { title: "Withdraw — RemitX" },
    { name: "robots", content: "noindex" },
  ]
}

export default function WithdrawPage() {
  const [searchParams] = useSearchParams()
  const accounts = useQuery(api.accounts.getAccounts())
  const fiat = accounts.data?.filter(canWithdrawFrom) ?? []

  return (
    <AppPageFrame module={ROUTE_MODULE}>
      <div className="flex flex-col gap-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <PageHeader>
            <PageHeaderTitle>Withdraw</PageHeaderTitle>
            <PageHeaderDescription>
              Move money from a RemitX account to your own bank account.
            </PageHeaderDescription>
          </PageHeader>
          <Button
            variant="outline"
            nativeButton={false}
            render={<Link to={BANK_ACCOUNTS_HREF} />}
          >
            <BankIcon data-icon="inline-start" />
            Bank accounts
          </Button>
        </div>

        {accounts.isPending ? (
          <Skeleton className="h-80" />
        ) : accounts.isError ? (
          <QueryError
            title="Couldn't load your accounts"
            error={accounts.error}
            onRetry={() => accounts.refetch()}
          />
        ) : fiat.length === 0 ? (
          <Empty className="border">
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <ArrowCircleUpIcon />
              </EmptyMedia>
              <EmptyTitle>Nothing to withdraw from</EmptyTitle>
              <EmptyDescription>
                You need a currency account before you can withdraw.
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          <WithdrawForm
            // A new ?currency= (an account card's Withdraw) starts afresh.
            key={searchParams.get("currency") ?? ""}
            accounts={fiat}
            initialCurrency={searchParams.get("currency")}
          />
        )}

        <section className="flex flex-col gap-4" aria-labelledby="history">
          <h2 id="history" className="font-heading text-lg font-semibold">
            Past withdrawals
          </h2>
          <WithdrawalHistory />
        </section>
      </div>
    </AppPageFrame>
  )
}

function WithdrawalHistory() {
  const withdrawals = useQuery(api.withdrawals.listWithdrawals())
  // Names each row's destination. The masked number is all the customer
  // API gives, which is all the row needs.
  const bankAccounts = useQuery(api.bank_accounts.listBankAccounts())

  if (withdrawals.isPending) return <Skeleton className="h-40 w-full" />
  if (withdrawals.isError) {
    return (
      <QueryError
        title="Couldn't load your withdrawals"
        error={withdrawals.error}
        onRetry={() => withdrawals.refetch()}
      />
    )
  }
  if (withdrawals.data.length === 0) {
    return (
      <Empty className="border">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <ArrowCircleUpIcon />
          </EmptyMedia>
          <EmptyTitle>No withdrawals yet</EmptyTitle>
          <EmptyDescription>
            Money you withdraw to your bank shows up here.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }
  return (
    <WithdrawalsTable
      withdrawals={withdrawals.data}
      bankAccounts={bankAccounts.data ?? []}
    />
  )
}
