import type { AccountRead } from "~/client"
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

export function accountTitle(account: AccountRead) {
  return account.kind === "settlement"
    ? "RLUSD wallet · XRPL Testnet"
    : currencyName(account.currency)
}

/** Sidebar label. Shorter than `accountTitle` so the settlement wallet fits
 * on one line; the testnet qualifier stays on the page. */
export function accountNavLabel(account: AccountRead) {
  return account.kind === "settlement"
    ? "RLUSD wallet"
    : currencyName(account.currency)
}

/**
 * Demo bank details for Add money. Nothing is ever paid into these: deposits
 * reach a balance only when staff upload a statement on
 * /admin/process-deposits.
 */
export const DEMO_BANK_DETAILS = {
  accountName: "RemitX SA",
  bank: "RemitX Demo Bank",
  accountNumber: "1000 2000 3000",
  branchCode: "999 000",
} as const
