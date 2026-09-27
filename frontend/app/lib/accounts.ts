import type { QueryClient } from "@tanstack/react-query"

import { api, PayoutCurrency, type AccountRead } from "~/client"
import { currencyName } from "~/lib/money"

export const ACCOUNTS_HREF = "/app/accounts"

/** Where a transfer is started. Built by SEND-1 (#106). */
export const SEND_HREF = "/app/send"

export function accountHref(accountId: string) {
  return `${ACCOUNTS_HREF}/${accountId}`
}

/** Deposits are EFTs into RemitX's South African account, matched when staff
 * reconcile the bank statement, so only the ZAR account takes one. */
export function acceptsDeposits(account: AccountRead) {
  return account.kind === "fiat" && account.currency === "ZAR"
}

/** Fiat payout currencies the user does not hold yet (ZAR, USD, ZWL, NAD). */
export function openablePayoutCurrencies(
  heldCurrencies: readonly string[]
): PayoutCurrency[] {
  const held = new Set(heldCurrencies)
  return (Object.values(PayoutCurrency) as PayoutCurrency[]).filter(
    (currency) => !held.has(currency)
  )
}

export async function invalidateAccounts(queryClient: QueryClient) {
  await queryClient.invalidateQueries({
    queryKey: api.accounts.getAccounts().queryKey,
  })
}

export function accountTitle(account: AccountRead) {
  return account.kind === "settlement"
    ? "UCTUSD wallet · XRPL Testnet"
    : currencyName(account.currency)
}

/** Sidebar label. Shorter than `accountTitle` so the settlement wallet fits
 * on one line; the testnet qualifier stays on the page. */
export function accountNavLabel(account: AccountRead) {
  return account.kind === "settlement"
    ? "UCTUSD wallet"
    : currencyName(account.currency)
}

/**
 * Demo bank details for Add money. Nothing is ever paid into these: deposits
 * reach a balance only when staff upload a statement on
 * /admin/process-deposits. The file itself is built on /admin/statement-csv.
 * Both pages are limited to the cash-in role.
 */
export const DEMO_BANK_DETAILS = {
  accountName: "RemitX SA",
  bank: "RemitX Demo Bank",
  accountNumber: "1000 2000 3000",
  branchCode: "999 000",
} as const
