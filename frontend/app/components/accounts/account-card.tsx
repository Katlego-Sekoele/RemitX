import {
  CaretDownIcon,
  ClockCountdownIcon,
  ListBulletsIcon,
  PlusIcon,
} from "@phosphor-icons/react"
import { Link } from "react-router"

import type { AccountRead } from "~/client"
import { AccountReference } from "~/components/accounts/reference"
import { Button } from "~/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import { CollapsibleTrigger } from "~/components/ui/collapsible"
import {
  DescriptionDetails,
  DescriptionItem,
  DescriptionList,
  DescriptionTerm,
} from "~/components/ui/description-list"
import { accountHref, acceptsDeposits, accountTitle } from "~/lib/accounts"
import {
  SETTLEMENT_TOKEN_NOTE,
  currencyLabel,
  formatMoney,
  isZeroMoney,
  subtractMoney,
} from "~/lib/money"

/**
 * One currency account: what's spendable, what's still in flight, the
 * reference that identifies it, and what the account is for. The ZAR card's
 * Add money toggles the page's inline Add money panel (see
 * routes/app/accounts.tsx), so it must render inside that Collapsible.
 */
export function AccountCard({ account }: { account: AccountRead }) {
  const settlement = account.kind === "settlement"
  // `available_balance` nets out this account's own in-flight outgoing legs,
  // so the gap between the two is what's pending.
  const pending = subtractMoney(account.balance, account.available_balance)
  const money = (amount: string) =>
    formatMoney(amount, account.currency, account.kind)

  return (
    <Card>
      <CardHeader>
        <CardTitle>{accountTitle(account)}</CardTitle>
        <CardDescription>
          {settlement
            ? SETTLEMENT_TOKEN_NOTE
            : currencyLabel(account.currency, account.kind)}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <DescriptionList>
          <DescriptionItem>
            {/* The settlement wallet only ever passes money through: its
                pending legs go out before the matching legs in confirm, so
                "available" would briefly read negative there. Its ledger
                balance is the honest figure. */}
            <DescriptionTerm>
              {settlement ? "Balance" : "Available"}
            </DescriptionTerm>
            <DescriptionDetails className="font-heading text-2xl font-semibold tabular-nums">
              {money(settlement ? account.balance : account.available_balance)}
            </DescriptionDetails>
          </DescriptionItem>
          {isZeroMoney(pending) ? null : (
            <DescriptionItem>
              <DescriptionTerm className="inline-flex items-center gap-1">
                <ClockCountdownIcon aria-hidden="true" />
                {settlement ? "Settling" : "Pending"}
              </DescriptionTerm>
              <DescriptionDetails className="tabular-nums">
                {money(pending)}
              </DescriptionDetails>
            </DescriptionItem>
          )}
          <DescriptionItem wide>
            <DescriptionTerm>Reference</DescriptionTerm>
            <DescriptionDetails>
              <AccountReference reference={account.reference} />
            </DescriptionDetails>
          </DescriptionItem>
        </DescriptionList>
        <CardDescription>{purpose(account)}</CardDescription>
      </CardContent>
      <CardFooter className="gap-2">
        {acceptsDeposits(account) ? (
          <CollapsibleTrigger render={<Button />}>
            <PlusIcon data-icon="inline-start" />
            Add money
            <CaretDownIcon data-icon="inline-end" />
          </CollapsibleTrigger>
        ) : null}
        <Button
          variant="outline"
          nativeButton={false}
          render={<Link to={accountHref(account.account_id)} />}
        >
          <ListBulletsIcon data-icon="inline-start" />
          History
        </Button>
      </CardFooter>
    </Card>
  )
}

function purpose(account: AccountRead): string {
  if (account.kind === "settlement") {
    return "Transfers settle through this wallet on the XRP Ledger Testnet. RLUSD you receive is converted into your payout currency automatically."
  }
  if (acceptsDeposits(account)) {
    return "Add money by EFT, quoting this reference. Share it so a sender can add you and pay you in ZAR."
  }
  return `Share this reference so a sender can add you and pay you in ${account.currency}.`
}
