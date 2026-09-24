import { BankIcon } from "@phosphor-icons/react"

import type { BankAccountRead } from "~/client"
import { Badge } from "~/components/ui/badge"
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemMedia,
  ItemTitle,
} from "~/components/ui/item"
import { Skeleton } from "~/components/ui/skeleton"
import { bankAccountLabel, bankAccountStatus } from "~/lib/withdrawals"

export function BankAccountStatusBadge({ status }: { status: string }) {
  const { label, variant } = bankAccountStatus(status)
  return <Badge variant={variant}>{label}</Badge>
}

/** The customer's own bank accounts, in any status. A rejected one says why,
 * so the customer knows what to fix when they add it again. */
export function BankAccountList({
  accounts,
}: {
  accounts: readonly BankAccountRead[]
}) {
  return (
    <ItemGroup>
      {accounts.map((account) => (
        <Item key={account.bank_account_id} variant="outline" role="listitem">
          <ItemMedia variant="icon">
            <BankIcon />
          </ItemMedia>
          <ItemContent className="min-w-0">
            <ItemTitle>{bankAccountLabel(account)}</ItemTitle>
            <ItemDescription>
              {[account.account_holder_name, account.branch_code]
                .filter(Boolean)
                .join(" · ")}
            </ItemDescription>
            {account.status === "rejected" && account.rejection_reason ? (
              <ItemDescription>
                Rejected: {account.rejection_reason}
              </ItemDescription>
            ) : null}
          </ItemContent>
          <ItemActions>
            <Badge variant="secondary">{account.currency}</Badge>
            <BankAccountStatusBadge status={account.status} />
          </ItemActions>
        </Item>
      ))}
    </ItemGroup>
  )
}

export function BankAccountListSkeleton() {
  return (
    <ItemGroup aria-busy="true" aria-label="Loading bank accounts">
      {[0, 1].map((index) => (
        <Item key={index} variant="outline">
          <ItemMedia variant="icon">
            <Skeleton className="size-4" />
          </ItemMedia>
          <ItemContent>
            <Skeleton className="h-3.5 w-40" />
            <Skeleton className="h-3 w-56" />
          </ItemContent>
          <ItemActions>
            <Skeleton className="h-5 w-24" />
          </ItemActions>
        </Item>
      ))}
    </ItemGroup>
  )
}
