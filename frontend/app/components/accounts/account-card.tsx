import {
  CaretDownIcon,
  ClockCountdownIcon,
  ListBulletsIcon,
  PlusIcon,
} from "@phosphor-icons/react"
import type { ReactNode } from "react"
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
  type AccountKind,
} from "~/lib/money"

type AccountCardFrameProps = {
  title: string
  description: string
  currency: string
  kind: AccountKind
  /** The headline figure and what it's called, e.g. "Available". */
  headline: { label: string; amount: string }
  /** Money still in flight and what it's called. Hidden when zero. */
  pending: { label: string; amount: string }
  /** Further `DescriptionItem`s under the figures, e.g. the reference. */
  details?: ReactNode
  /** What the account is for. */
  purpose: string
  footer?: ReactNode
}

/**
 * The card every account is shown on — a customer's own on the Accounts page,
 * RemitX's platform accounts in the admin portal: its figures, whatever
 * identifies it, and what it's for.
 */
export function AccountCardFrame({
  title,
  description,
  currency,
  kind,
  headline,
  pending,
  details,
  purpose,
  footer,
}: AccountCardFrameProps) {
  const money = (amount: string) => formatMoney(amount, currency, kind)

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <DescriptionList>
          <DescriptionItem>
            <DescriptionTerm>{headline.label}</DescriptionTerm>
            <DescriptionDetails className="font-heading text-2xl font-semibold tabular-nums">
              {money(headline.amount)}
            </DescriptionDetails>
          </DescriptionItem>
          {isZeroMoney(pending.amount) ? null : (
            <DescriptionItem>
              <DescriptionTerm className="inline-flex items-center gap-1">
                <ClockCountdownIcon aria-hidden="true" />
                {pending.label}
              </DescriptionTerm>
              <DescriptionDetails className="tabular-nums">
                {money(pending.amount)}
              </DescriptionDetails>
            </DescriptionItem>
          )}
          {details}
        </DescriptionList>
        <CardDescription>{purpose}</CardDescription>
      </CardContent>
      {footer ? <CardFooter className="gap-2">{footer}</CardFooter> : null}
    </Card>
  )
}

/**
 * One currency account: what's spendable, what's still in flight, the
 * reference that identifies it, and what the account is for. The ZAR card's
 * Add money toggles the page's inline Add money panel (see
 * routes/app/accounts.tsx), so it must render inside that Collapsible.
 */
export function AccountCard({ account }: { account: AccountRead }) {
  const settlement = account.kind === "settlement"

  return (
    <AccountCardFrame
      title={accountTitle(account)}
      description={
        settlement
          ? SETTLEMENT_TOKEN_NOTE
          : currencyLabel(account.currency, account.kind)
      }
      currency={account.currency}
      kind={account.kind}
      // The settlement wallet only ever passes money through: its pending
      // legs go out before the matching legs in confirm, so "available"
      // would briefly read negative there. Its ledger balance is the honest
      // figure.
      headline={
        settlement
          ? { label: "Balance", amount: account.balance }
          : { label: "Available", amount: account.available_balance }
      }
      // `available_balance` nets out this account's own in-flight outgoing
      // legs, so the gap between the two is what's pending.
      pending={{
        label: settlement ? "Settling" : "Pending",
        amount: subtractMoney(account.balance, account.available_balance),
      }}
      details={
        <DescriptionItem wide>
          <DescriptionTerm>Reference</DescriptionTerm>
          <DescriptionDetails>
            <AccountReference reference={account.reference} />
          </DescriptionDetails>
        </DescriptionItem>
      }
      purpose={purpose(account)}
      footer={
        <>
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
        </>
      }
    />
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
