import type { QueryClient } from "@tanstack/react-query"
import type { VariantProps } from "class-variance-authority"

import { api, type AccountRead, type BankAccountRead } from "~/client"
import type { badgeVariants } from "~/components/ui/badge"
import { amountToCents, toCents } from "~/lib/money"

type BadgeVariant = NonNullable<VariantProps<typeof badgeVariants>["variant"]>

export const WITHDRAW_HREF = "/app/withdraw"
export const BANK_ACCOUNTS_HREF = "/app/bank-accounts"

/** The Withdraw page with this currency's account already chosen. */
export function withdrawHref(currency: string) {
  return `${WITHDRAW_HREF}?currency=${encodeURIComponent(currency)}`
}

/** Money leaves RemitX from a fiat account only. The settlement wallet is a
 * pass-through; the API refuses a token withdrawal outright. */
export function canWithdrawFrom(account: AccountRead) {
  return account.kind === "fiat"
}

const BANK_ACCOUNT_STATUS: Record<
  string,
  { label: string; variant: BadgeVariant }
> = {
  pending_verification: { label: "Awaiting verification", variant: "outline" },
  verified: { label: "Verified", variant: "default" },
  rejected: { label: "Rejected", variant: "destructive" },
}

/** A bank account's verification status as the customer and staff read it. */
export function bankAccountStatus(status: string) {
  return (
    BANK_ACCOUNT_STATUS[status] ?? {
      label: status,
      variant: "outline" as const,
    }
  )
}

/** "FNB ****7890". The customer API already masks the number; the admin API
 * sends it in full. */
export function bankAccountLabel(
  account: Pick<BankAccountRead, "bank_name" | "account_number">
) {
  return `${account.bank_name} ${account.account_number}`
}

// A withdrawal settles in the request that makes it, so its status is the
// payout leg's: confirmed once it has settled, failed if it was refused.
const WITHDRAWAL_STATUS: Record<
  string,
  { label: string; variant: BadgeVariant }
> = {
  pending: { label: "Processing", variant: "outline" },
  processing: { label: "Processing", variant: "outline" },
  confirmed: { label: "Paid out", variant: "default" },
  failed: { label: "Failed", variant: "destructive" },
}

export function withdrawalStatus(status: string) {
  return (
    WITHDRAWAL_STATUS[status] ?? { label: status, variant: "outline" as const }
  )
}

/**
 * Why this amount can't be withdrawn, or `null` if it can be sent. Checked
 * before the request so the customer hears it at once; the API repeats every
 * check, and also refuses anything under its minimum after the fee.
 */
export function withdrawalAmountError(
  amount: string,
  available: string
): string | null {
  if (!amount.trim()) return "Enter an amount."
  const cents = toCents(amount)
  if (cents === null) return "Enter an amount with up to two decimal places."
  if (cents === 0n) return "Enter an amount above zero."
  if (cents > amountToCents(available)) {
    return "That's more than your available balance."
  }
  return null
}

/** After a bank account is added. Keys match partially, so the bare keys
 * cover every currency filter. */
export function invalidateBankAccounts(queryClient: QueryClient) {
  return Promise.all([
    queryClient.invalidateQueries({
      queryKey: api.bank_accounts.listBankAccounts().queryKey,
    }),
    queryClient.invalidateQueries({
      queryKey: [{ _id: "listWithdrawableBankAccounts" }],
    }),
  ])
}

/** A withdrawal moves the balance and adds a history row. */
export function invalidateAfterWithdrawal(queryClient: QueryClient) {
  return Promise.all([
    queryClient.invalidateQueries({
      queryKey: api.withdrawals.listWithdrawals().queryKey,
    }),
    queryClient.invalidateQueries({
      queryKey: api.accounts.getAccounts().queryKey,
    }),
  ])
}
