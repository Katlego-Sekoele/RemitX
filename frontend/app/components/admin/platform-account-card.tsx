import type { PlatformAccountRead } from "~/client"
import { AccountCardFrame } from "~/components/accounts/account-card"
import { currencyLabel, subtractMoney } from "~/lib/money"

type PlatformAccountType = PlatformAccountRead["type"]

const TYPE_LABEL: Record<PlatformAccountType, string> = {
  REMITX_FIAT: "Bank account",
  REMITX_REVENUE: "Fee revenue",
  REMITX_XRPL_WALLET: "Treasury wallet",
  EXTERNAL: "External counterparty",
}

/**
 * One of RemitX's own accounts, on the same card a customer's account uses.
 * The headline is the ledger balance, which can be negative: a deposit is
 * booked out of the bank account into the customer's, and the issuer has
 * paid out what the treasury wallet holds.
 */
export function PlatformAccountCard({
  account,
}: {
  account: PlatformAccountRead
}) {
  const currency = currencyLabel(account.currency, account.kind)

  return (
    <AccountCardFrame
      title={account.label}
      description={`${TYPE_LABEL[account.type]} · ${currency}`}
      currency={account.currency}
      kind={account.kind}
      headline={{ label: "Balance", amount: account.balance }}
      // `available_balance` nets out this account's own in-flight outgoing
      // legs, so the gap between the two is what's still leaving it.
      pending={{
        label: "Pending out",
        amount: subtractMoney(account.balance, account.available_balance),
      }}
      purpose={purpose(account.type, currency)}
    />
  )
}

function purpose(type: PlatformAccountType, currency: string): string {
  switch (type) {
    case "REMITX_FIAT":
      return `RemitX's bank account in ${currency}. Customer deposits, transfers sent in ${currency} and payouts made in it are all booked against it.`
    case "REMITX_REVENUE":
      return `The transfer fee and FX margin earned on transfers sent in ${currency}.`
    case "REMITX_XRPL_WALLET":
      return "Every transfer settles through this wallet on the XRP Ledger Testnet, and its RLUSD is burned back to the issuer from here."
    case "EXTERNAL":
      return "The RLUSD issuer. It pre-funded the treasury wallet, and every burn returns RLUSD to it."
  }
}
