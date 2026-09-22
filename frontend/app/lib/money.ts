import type { AccountRead } from "~/client"

/**
 * Money on screen. The API sends amounts as 2 dp decimal strings; nothing
 * here turns one into a float. `Intl.NumberFormat` formats the string
 * itself, exactly, and the little arithmetic the UI needs is done in whole
 * cents with BigInt.
 */

export type AccountKind = AccountRead["kind"]

/** What the UI calls the settlement token, whatever the API names it. */
export const SETTLEMENT_TOKEN_LABEL = "RLUSD"

/** Said once, wherever the token first appears on a page. */
export const SETTLEMENT_TOKEN_NOTE =
  "Test token on the XRP Ledger Testnet, the lecturer-approved stand-in for RLUSD."

const CURRENCY_NAMES: Record<string, string> = {
  ZAR: "South African rand",
  USD: "US dollar",
  ZWL: "Zimbabwean dollar",
  NAD: "Namibian dollar",
}

// Local symbols that don't collide with another currency RemitX handles.
// USD and NAD both write "$", so they keep their codes.
const SYMBOLS: Record<string, string> = { ZAR: "R" }

type Sign = "auto" | "always" | "exceptZero" | "never"

export function currencyLabel(currency: string, kind: AccountKind = "fiat") {
  return kind === "settlement" ? SETTLEMENT_TOKEN_LABEL : currency
}

export function currencyName(currency: string, kind: AccountKind = "fiat") {
  if (kind === "settlement") return SETTLEMENT_TOKEN_LABEL
  return CURRENCY_NAMES[currency] ?? currency
}

/** "R 1,000.00", "ZWL 1,354.37", "RLUSD 54.05". */
export function formatMoney(
  amount: string,
  currency: string,
  kind: AccountKind = "fiat",
  signDisplay: Sign = "auto"
): string {
  const value = amount as Intl.StringNumericLiteral

  if (kind === "settlement") {
    const number = new Intl.NumberFormat("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
      signDisplay,
    }).formatToParts(value)
    const sign = number.filter((part) => part.type.endsWith("Sign"))
    const digits = number.filter((part) => !part.type.endsWith("Sign"))
    return `${join(sign)}${SETTLEMENT_TOKEN_LABEL} ${join(digits)}`
  }

  const parts = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    currencyDisplay: "code",
    signDisplay,
  }).formatToParts(value)
  const symbol = SYMBOLS[currency]
  return join(
    parts.map((part) =>
      part.type === "currency" && symbol ? { ...part, value: symbol } : part
    )
  )
}

function join(parts: Intl.NumberFormatPart[]): string {
  return parts.map((part) => part.value).join("")
}

function toCents(amount: string): bigint {
  const trimmed = amount.trim()
  const negative = trimmed.startsWith("-")
  const [whole, fraction = ""] = trimmed.replace(/^[-+]/, "").split(".")
  const cents =
    BigInt(whole || "0") * 100n + BigInt(`${fraction}00`.slice(0, 2))
  return negative ? -cents : cents
}

function fromCents(cents: bigint): string {
  const negative = cents < 0n
  const magnitude = negative ? -cents : cents
  const fraction = (magnitude % 100n).toString().padStart(2, "0")
  return `${negative ? "-" : ""}${magnitude / 100n}.${fraction}`
}

/** `a - b`, as a 2 dp decimal string. */
export function subtractMoney(a: string, b: string): string {
  return fromCents(toCents(a) - toCents(b))
}

/** The sum of 2 dp decimal strings, as one. */
export function sumMoney(amounts: readonly string[]): string {
  return fromCents(amounts.reduce((total, a) => total + toCents(a), 0n))
}

export function isZeroMoney(amount: string): boolean {
  return toCents(amount) === 0n
}
