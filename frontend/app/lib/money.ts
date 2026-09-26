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

/** The token's API name. Quote lines still carry this code. */
export const TOKEN_CURRENCY = "uctusd"

/** Quote lines use these names for the same token label and note. */
export const TOKEN_LABEL = SETTLEMENT_TOKEN_LABEL

/** Said once, wherever the token first appears on a page. */
export const SETTLEMENT_TOKEN_NOTE =
  "Test token on the XRP Ledger Testnet, the lecturer-approved stand-in for RLUSD."

export const TOKEN_NOTE = SETTLEMENT_TOKEN_NOTE

const CURRENCY_NAMES: Record<string, string> = {
  ZAR: "South African rand",
  USD: "US dollar",
  ZWL: "Zimbabwean dollar",
  NAD: "Namibian dollar",
}

// Local symbols that don't collide with another currency RemitX handles.
// USD and NAD both write "$", so they keep their codes.
const SYMBOLS: Record<string, string> = { ZAR: "R" }

/** "R" for rand, otherwise the currency's own code (`formatMoney`'s prefix,
 * for a line that builds its own string rather than calling it). */
export function currencySymbol(currency: string): string {
  return SYMBOLS[currency] ?? currency
}

type Sign = "auto" | "always" | "exceptZero" | "never"

const AMOUNT_PATTERN = /^\d+(\.\d{0,2})?$/

function isSettlement(currency: string, kind: AccountKind) {
  return kind === "settlement" || currency === TOKEN_CURRENCY
}

export function currencyLabel(currency: string, kind: AccountKind = "fiat") {
  return isSettlement(currency, kind) ? SETTLEMENT_TOKEN_LABEL : currency
}

export function currencyName(currency: string, kind: AccountKind = "fiat") {
  if (isSettlement(currency, kind)) return SETTLEMENT_TOKEN_LABEL
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

  if (isSettlement(currency, kind)) {
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

/**
 * The largest amount a customer may enter: what the ledger's Numeric(20,8)
 * columns hold, to the cent (999 999 999 999.99). Not a business limit —
 * KYC limits refuse real sends far below it — but anything larger is refused
 * by the API, so the forms say so before sending.
 */
export const MAX_AMOUNT_CENTS = 99_999_999_999_999n

/**
 * "1000.5" → 100050n. `null` for anything that isn't a plain, non-negative
 * amount with at most two decimal places. Typed amounts use this; stored
 * decimals use `amountToCents`.
 */
export function toCents(value: string): bigint | null {
  const trimmed = value.trim()
  if (!AMOUNT_PATTERN.test(trimmed)) return null
  const [whole, fraction = ""] = trimmed.split(".")
  return BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"))
}

/** 100050n → "1000.50". */
export function fromCents(cents: bigint): string {
  const negative = cents < 0n
  const magnitude = negative ? -cents : cents
  const fraction = (magnitude % 100n).toString().padStart(2, "0")
  return `${negative ? "-" : ""}${magnitude / 100n}.${fraction}`
}

/**
 * The API's decimal strings are always 2 dp, but a stored value can carry
 * trailing zeros ("12.50000000"). Accept those too, and refuse anything that
 * would lose a cent.
 */
/**
 * Pydantic may JSON-encode a zero Numeric(20,8) as ``0E-8``. Expand exponent
 * form to a plain decimal string without using floats.
 */
function expandScientificDecimal(value: string): string {
  const trimmed = value.trim()
  if (!/[eE]/.test(trimmed)) return trimmed
  const negative = trimmed.startsWith("-")
  const body = trimmed.replace(/^[-+]/, "")
  const [coeff, expPart] = body.split(/[eE]/)
  if (expPart === undefined) return trimmed
  const exp = Number(expPart)
  if (!Number.isInteger(exp)) return trimmed
  const [intPart, fracPart = ""] = coeff.split(".")
  const digits = intPart + fracPart
  const decimalIndex = intPart.length + exp
  if (decimalIndex <= 0) {
    return `${negative ? "-" : ""}0.${"0".repeat(-decimalIndex)}${digits}`
  }
  if (decimalIndex >= digits.length) {
    return `${negative ? "-" : ""}${digits}${"0".repeat(decimalIndex - digits.length)}`
  }
  return `${negative ? "-" : ""}${digits.slice(0, decimalIndex)}.${digits.slice(decimalIndex)}`
}

export function amountToCents(value: string): bigint {
  const normalized = expandScientificDecimal(value)
  const match = /^(-?)(\d+)(?:\.(\d*))?$/.exec(normalized.trim())
  if (!match) throw new Error(`Not a decimal amount: ${value}`)
  const [, sign, whole, fraction = ""] = match
  if (/[1-9]/.test(fraction.slice(2))) {
    throw new Error(`More than 2 decimal places: ${value}`)
  }
  const cents =
    BigInt(whole) * 100n + BigInt(fraction.slice(0, 2).padEnd(2, "0"))
  return sign ? -cents : cents
}

function parseCents(amount: string): bigint {
  return amountToCents(amount)
}

/** `a − b − …` on 2 dp decimal strings, exactly. */
export function subtractAmounts(from: string, ...amounts: string[]): string {
  return fromCents(
    amounts.reduce(
      (total, amount) => total - amountToCents(amount),
      amountToCents(from)
    )
  )
}

/** `a - b`, as a 2 dp decimal string. */
export function subtractMoney(a: string, b: string): string {
  return fromCents(parseCents(a) - parseCents(b))
}

/** The sum of 2 dp decimal strings, as one. */
export function sumMoney(amounts: readonly string[]): string {
  return fromCents(amounts.reduce((total, a) => total + parseCents(a), 0n))
}

export function isZeroMoney(amount: string): boolean {
  return parseCents(amount) === 0n
}

const RATE_DP = 4

const rateFormatter = new Intl.NumberFormat("en", {
  minimumFractionDigits: RATE_DP,
  maximumFractionDigits: RATE_DP,
})

/** Rates display to 4 dp: "18.5000". */
export function formatRate(rate: string): string {
  return rateFormatter.format(rate as unknown as number)
}

/**
 * `1 / rate` to `dp` places, rounded half up, without floats. The API prices
 * the token leg as token units per 1 ZAR (0.05405405); people read it the
 * other way round, as rand per dollar (18.5000).
 */
export function invertRate(rate: string, dp: number = RATE_DP): string {
  const match = /^(\d+)(?:\.(\d+))?$/.exec(rate.trim())
  if (!match) throw new Error(`Not a positive rate: ${rate}`)
  const [, whole, fraction = ""] = match
  const scale = 10n ** BigInt(fraction.length)
  const numerator = BigInt(whole + fraction)
  if (numerator === 0n) throw new Error("Cannot invert a zero rate")
  // 1 / (numerator / scale) = scale / numerator; scaled by 10^dp, then
  // rounded half up by adding half the divisor before dividing.
  const target = 10n ** BigInt(dp)
  const quotient = (2n * scale * target + numerator) / (2n * numerator)
  const digits = quotient.toString().padStart(dp + 1, "0")
  return dp === 0 ? digits : `${digits.slice(0, -dp)}.${digits.slice(-dp)}`
}

/**
 * How many units of `senderCurrency` buy one settlement token. The API's
 * `fiat_to_token_exchange_rate` is token per sender unit; people read the
 * inverse, with the quote's token label and sender currency.
 */
export function formatFiatToTokenExchangeRate(
  fiatToTokenExchangeRate: string,
  senderCurrency: string,
  tokenName: string
): string {
  const token = currencyLabel(tokenName, "settlement")
  const sender = SYMBOLS[senderCurrency] ?? senderCurrency
  return `1 ${token} = ${sender} ${formatRate(invertRate(fiatToTokenExchangeRate))}`
}
