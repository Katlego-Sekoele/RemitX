import { ArrowRightIcon } from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router"

import { api } from "~/client"
import { QueryError } from "~/components/accounts/query-error"
import { Button } from "~/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
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
import { ACCOUNTS_HREF, accountHref } from "~/lib/accounts"
import { currencyName, formatMoney } from "~/lib/money"

/** The available balance of each fiat account, for the overview. The
 * settlement wallet only passes money through, so it's left to the Accounts
 * page. */
export function BalanceSummary() {
  const accounts = useQuery(api.accounts.getAccounts())

  return (
    <Card>
      <CardHeader>
        <CardTitle>Balances</CardTitle>
        <CardAction>
          <Button
            variant="ghost"
            size="sm"
            nativeButton={false}
            render={<Link to={ACCOUNTS_HREF} />}
          >
            All accounts
            <ArrowRightIcon data-icon="inline-end" />
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        {accounts.isPending ? (
          <Skeleton className="h-12" />
        ) : accounts.isError ? (
          <QueryError
            title="Couldn't load your balances"
            error={accounts.error}
            onRetry={() => accounts.refetch()}
          />
        ) : (
          <DescriptionList>
            {accounts.data
              .filter((account) => account.kind === "fiat")
              .map((account) => (
                <DescriptionItem key={account.account_id}>
                  <DescriptionTerm>
                    <Link to={accountHref(account.account_id)}>
                      {currencyName(account.currency)} · {account.currency}
                    </Link>
                  </DescriptionTerm>
                  <DescriptionDetails className="font-heading text-2xl font-semibold tabular-nums">
                    {formatMoney(account.available_balance, account.currency)}
                  </DescriptionDetails>
                </DescriptionItem>
              ))}
          </DescriptionList>
        )}
      </CardContent>
    </Card>
  )
}
