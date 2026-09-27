import {
  ArrowsClockwiseIcon,
  CaretDownIcon,
  CaretRightIcon,
  ReceiptIcon,
} from "@phosphor-icons/react"
import { useInfiniteQuery, useQuery } from "@tanstack/react-query"
import { Fragment, useState } from "react"
import { Link, useParams } from "react-router"

import { api, sdk, type AccountRead } from "~/client"
import { QueryError } from "~/components/accounts/query-error"
import { AccountReference } from "~/components/accounts/reference"
import { StatusBadge } from "~/components/accounts/status-badge"
import { AppPageFrame } from "~/components/app-dashboard/app-page-frame"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { Button } from "~/components/ui/button"
import {
  DescriptionDetails,
  DescriptionItem,
  DescriptionList,
  DescriptionTerm,
} from "~/components/ui/description-list"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "~/components/ui/empty"
import { PageHeader, PageHeaderTitle } from "~/components/ui/page-header"
import { Skeleton } from "~/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table"
import { TxHash } from "~/components/xrpl/tx-hash"
import {
  HISTORY_PAGE_SIZE,
  type HistoryRow,
  historyRows,
} from "~/lib/account-history"
import { ACCOUNTS_HREF, accountTitle } from "~/lib/accounts"
import { SETTLEMENT_TOKEN_NOTE, formatMoney } from "~/lib/money"
import { transferHref } from "~/lib/transfer-status"
import type { Route } from "./+types/account-history"

const ROUTE_MODULE = "routes/app/account-history.tsx"

export function meta(): Route.MetaDescriptors {
  return [
    { title: "Account history — RemitX" },
    { name: "robots", content: "noindex" },
  ]
}

export default function AccountHistoryPage() {
  const { accountId = "" } = useParams()
  const accounts = useQuery(api.accounts.getAccounts())
  const account = accounts.data?.find((item) => item.account_id === accountId)

  return (
    <AppPageFrame
      module={ROUTE_MODULE}
      title={account ? accountTitle(account) : "History"}
      parents={[{ label: "Accounts", href: ACCOUNTS_HREF }]}
    >
      <div className="flex flex-col gap-6">
        {accounts.isPending ? (
          <Skeleton className="h-24" />
        ) : accounts.isError ? (
          <QueryError
            title="Couldn't load this account"
            error={accounts.error}
            onRetry={() => accounts.refetch()}
          />
        ) : account ? (
          <>
            <AccountHeader account={account} />
            <History account={account} />
          </>
        ) : (
          <Empty className="border">
            <EmptyHeader>
              <EmptyTitle>Account not found</EmptyTitle>
              <EmptyDescription>
                It isn&apos;t one of your accounts.{" "}
                <Link to={ACCOUNTS_HREF}>Back to your accounts</Link>
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        )}
      </div>
    </AppPageFrame>
  )
}

function AccountHeader({ account }: { account: AccountRead }) {
  const settlement = account.kind === "settlement"
  return (
    <div className="flex flex-col gap-4">
      <PageHeader>
        <PageHeaderTitle>{accountTitle(account)}</PageHeaderTitle>
      </PageHeader>
      <DescriptionList>
        <DescriptionItem>
          <DescriptionTerm>
            {settlement ? "Balance" : "Available"}
          </DescriptionTerm>
          <DescriptionDetails className="font-heading text-2xl font-semibold tabular-nums">
            {formatMoney(
              settlement ? account.balance : account.available_balance,
              account.currency,
              account.kind
            )}
          </DescriptionDetails>
        </DescriptionItem>
        <DescriptionItem>
          <DescriptionTerm>Reference</DescriptionTerm>
          <DescriptionDetails>
            <AccountReference reference={account.reference} />
          </DescriptionDetails>
        </DescriptionItem>
      </DescriptionList>
      {settlement ? (
        <Alert>
          <ArrowsClockwiseIcon />
          <AlertTitle>Why this balance returns to 0</AlertTitle>
          <AlertDescription>
            UCTUSD only passes through this wallet. When you send, your ZAR is
            converted to UCTUSD and paid straight to your recipient&apos;s
            wallet. When you receive, the UCTUSD is converted into your payout
            currency straight away. Each movement links to its settlement on the
            XRP Ledger Testnet. {SETTLEMENT_TOKEN_NOTE}
          </AlertDescription>
        </Alert>
      ) : null}
    </div>
  )
}

function History({ account }: { account: AccountRead }) {
  const accountId = account.account_id
  const history = useInfiniteQuery({
    // Its own key beneath the generated one, so invalidating
    // getAccountsHistory() still reaches it but a plain query can't collide
    // with its paged shape.
    queryKey: [
      ...api.accounts.getAccountsHistory({ query: { account_id: accountId } })
        .queryKey,
      "pages",
    ],
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam, signal }) => {
      const { data } = await sdk.accounts.getAccountsHistory({
        query: {
          account_id: accountId,
          limit: HISTORY_PAGE_SIZE,
          before: pageParam,
        },
        signal,
        throwOnError: true,
      })
      return data
    },
    // A full page may have more behind it. The cursor is the last row's
    // timestamp exactly as the API sent it, microseconds and all.
    getNextPageParam: (page) =>
      page.length === HISTORY_PAGE_SIZE
        ? page[page.length - 1].created_at
        : null,
  })

  if (history.isPending) {
    return (
      <div className="flex flex-col gap-2">
        <Skeleton className="h-8" />
        <Skeleton className="h-8" />
        <Skeleton className="h-8" />
      </div>
    )
  }
  // A failed "Load more" keeps the pages already loaded, so only a failed
  // first page replaces the table.
  if (!history.data) {
    return (
      <QueryError
        title="Couldn't load this account's history"
        error={history.error}
        onRetry={() => history.refetch()}
      />
    )
  }

  const rows = historyRows(history.data.pages.flat(), account.kind)

  if (rows.length === 0) {
    return (
      <Empty className="border">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <ReceiptIcon />
          </EmptyMedia>
          <EmptyTitle>Nothing here yet</EmptyTitle>
          <EmptyDescription>
            {account.kind === "settlement"
              ? "UCTUSD movements appear here when you send or receive a transfer."
              : "Deposits and transfers appear here once they happen."}
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="hidden sm:table-cell">Date</TableHead>
            <TableHead>Description</TableHead>
            <TableHead className="text-right">Amount</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>XRPL transaction</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <HistoryLine key={row.key} row={row} account={account} />
          ))}
        </TableBody>
      </Table>
      {history.hasNextPage ? (
        <Button
          variant="outline"
          className="self-center"
          onClick={() => history.fetchNextPage()}
          disabled={history.isFetchingNextPage}
        >
          {history.isFetchingNextPage ? "Loading…" : "Load more"}
        </Button>
      ) : null}
      {history.isFetchNextPageError ? (
        <QueryError
          title="Couldn't load more"
          error={history.error}
          onRetry={() => history.fetchNextPage()}
        />
      ) : null}
    </div>
  )
}

function HistoryLine({
  row,
  account,
}: {
  row: HistoryRow
  account: AccountRead
}) {
  const [expanded, setExpanded] = useState(false)
  const expandable = row.legs.length > 1
  const money = (amount: string, direction: string) =>
    formatMoney(
      direction === "in" ? amount : `-${amount}`,
      row.currency,
      account.kind,
      "always"
    )

  return (
    <Fragment>
      <TableRow>
        <TableCell className="hidden whitespace-nowrap sm:table-cell">
          {formatDateTime(row.created_at)}
        </TableCell>
        <TableCell className="min-w-44 whitespace-normal">
          {/* On a phone the date moves under the description, so the amount
              stays on screen. */}
          <div className="flex flex-col gap-0.5">
            <span className="text-muted-foreground sm:hidden">
              {formatDateTime(row.created_at)}
            </span>
            <span className="flex items-center gap-1">
              {expandable ? (
                <Button
                  variant="ghost"
                  size="icon-xs"
                  aria-expanded={expanded}
                  aria-label={
                    expanded ? "Hide the breakdown" : "Show the breakdown"
                  }
                  onClick={() => setExpanded((value) => !value)}
                >
                  {expanded ? <CaretDownIcon /> : <CaretRightIcon />}
                </Button>
              ) : null}
              {row.remittance_id ? (
                <Link to={transferHref(row.remittance_id)}>
                  {row.description}
                </Link>
              ) : (
                row.description
              )}
            </span>
            {row.fees ? (
              <span className="text-muted-foreground">
                {formatMoney(row.amount, row.currency)} incl.{" "}
                {formatMoney(row.fees, row.currency)} fees
              </span>
            ) : null}
          </div>
        </TableCell>
        <TableCell className="text-right whitespace-nowrap tabular-nums">
          {money(row.amount, row.direction)}
        </TableCell>
        <TableCell>
          <StatusBadge status={row.status} />
        </TableCell>
        <TableCell>
          {row.xrpl_tx_hash ? <TxHash hash={row.xrpl_tx_hash} /> : "—"}
        </TableCell>
      </TableRow>
      {expandable && expanded
        ? row.legs.map((leg) => (
            <TableRow key={leg.tx_id}>
              <TableCell className="hidden sm:table-cell" />
              <TableCell className="pl-8 text-muted-foreground">
                {leg.description}
              </TableCell>
              <TableCell className="text-right whitespace-nowrap text-muted-foreground tabular-nums">
                {money(leg.amount, leg.direction)}
              </TableCell>
              <TableCell />
              <TableCell />
            </TableRow>
          ))
        : null}
    </Fragment>
  )
}

function formatDateTime(value: string) {
  return new Date(value).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  })
}
