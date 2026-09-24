import { BankIcon } from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"
import { useState } from "react"

import { api } from "~/client"
import { QueryError } from "~/components/accounts/query-error"
import { AppPageFrame } from "~/components/app-dashboard/app-page-frame"
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
import {
  AddBankAccountButton,
  AddBankAccountForm,
} from "~/components/withdrawals/add-bank-account-form"
import {
  BankAccountList,
  BankAccountListSkeleton,
} from "~/components/withdrawals/bank-account-list"
import type { Route } from "./+types/bank-accounts"

const ROUTE_MODULE = "routes/app/bank-accounts.tsx"

export function meta(): Route.MetaDescriptors {
  return [
    { title: "Bank accounts — RemitX" },
    { name: "robots", content: "noindex" },
  ]
}

export default function BankAccountsPage() {
  const [adding, setAdding] = useState(false)
  const bankAccounts = useQuery(api.bank_accounts.listBankAccounts())

  return (
    <AppPageFrame module={ROUTE_MODULE}>
      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <PageHeader>
            <PageHeaderTitle>Bank accounts</PageHeaderTitle>
            <PageHeaderDescription>
              Your own accounts at other banks, where withdrawals are paid. We
              verify each one before it can receive money.
            </PageHeaderDescription>
          </PageHeader>
          <AddBankAccountButton
            disabled={adding}
            onClick={() => setAdding(true)}
          />
        </div>

        {adding ? (
          <AddBankAccountForm
            onCancel={() => setAdding(false)}
            onAdded={() => setAdding(false)}
          />
        ) : null}

        {bankAccounts.isPending ? (
          <BankAccountListSkeleton />
        ) : bankAccounts.isError ? (
          <QueryError
            title="Couldn't load your bank accounts"
            error={bankAccounts.error}
            onRetry={() => bankAccounts.refetch()}
          />
        ) : bankAccounts.data.length > 0 ? (
          <BankAccountList accounts={bankAccounts.data} />
        ) : adding ? null : (
          <Empty className="border">
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <BankIcon />
              </EmptyMedia>
              <EmptyTitle>No bank accounts yet</EmptyTitle>
              <EmptyDescription>
                Add the account you want withdrawals paid into.
              </EmptyDescription>
            </EmptyHeader>
            <EmptyContent>
              <AddBankAccountButton onClick={() => setAdding(true)} />
            </EmptyContent>
          </Empty>
        )}
      </div>
    </AppPageFrame>
  )
}
