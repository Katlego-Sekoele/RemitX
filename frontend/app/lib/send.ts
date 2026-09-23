/**
 * The send flow's state and rules, kept out of the components so they can be
 * tested on their own. The flow's state lives in the URL's search params
 * (`/app/send?beneficiary=…&amount=…&currency=…&step=…`), so browser back,
 * a reload and the stepper's own triggers never lose it.
 */

import type { PayoutCurrency, QuoteRead as Quote } from "~/client"
import { formatMoney, formatRate, SETTLEMENT_TOKEN_LABEL } from "~/lib/money"

export const SEND_STEPS = [
  { key: "recipient", title: "Recipient" },
  { key: "amount", title: "Amount" },
  { key: "review", title: "Review" },
  { key: "sent", title: "Sent" },
] as const

export type SendStep = (typeof SEND_STEPS)[number]["key"]

/** The step the page can show; Sent is the transfer's own page (SEND-3). */
export type SendPageStep = Exclude<SendStep, "sent">

export type { PayoutCurrency }

/**
 * What a beneficiary can be paid out in, as options for a select. The type
 * comes from the API's enum, including the ZAR account from signup.
 */
export const PAYOUT_CURRENCIES = [
  "ZAR",
  "USD",
  "ZWL",
  "NAD",
] as const satisfies readonly PayoutCurrency[]

export function isPayoutCurrency(value: unknown): value is PayoutCurrency {
  return PAYOUT_CURRENCIES.includes(value as PayoutCurrency)
}

/** Sending is from the ZAR account only (decision 2 on #103). */
export const SENDER_CURRENCY = "ZAR"

/** How long the amount must sit still before the preview is requested. */
export const PREVIEW_DEBOUNCE_MS = 400

export type SendSearch = {
  beneficiaryId: string | null
  /** As typed; validated separately. */
  amount: string
  /** A per-transfer override of the beneficiary's payout currency. */
  currency: PayoutCurrency | null
  /** The step the URL asks for, before `resolveStep` checks it. */
  step: SendPageStep | null
}

export function readSendSearch(params: URLSearchParams): SendSearch {
  const step = params.get("step")
  const currency = params.get("currency")
  return {
    beneficiaryId: params.get("beneficiary") || null,
    amount: params.get("amount") ?? "",
    currency: isPayoutCurrency(currency) ? currency : null,
    step:
      step === "recipient" || step === "amount" || step === "review"
        ? step
        : null,
  }
}

/**
 * The search params for `patch` applied to `current`. Empty values drop their
 * key rather than leaving `?amount=` behind.
 */
export function writeSendSearch(
  current: SendSearch,
  patch: Partial<SendSearch>
): URLSearchParams {
  const next = { ...current, ...patch }
  const params = new URLSearchParams()
  if (next.beneficiaryId) params.set("beneficiary", next.beneficiaryId)
  if (next.amount) params.set("amount", next.amount)
  if (next.currency) params.set("currency", next.currency)
  if (next.step) params.set("step", next.step)
  return params
}

/**
 * The step to show. A step can't be reached without what it needs: Amount
 * needs a recipient, Review needs a valid amount too. `?beneficiary=<id>`
 * alone skips straight to Amount, which is what BEN-2's "Send money" uses.
 */
export function resolveStep(
  search: SendSearch,
  amountIsValid: boolean
): SendPageStep {
  if (!search.beneficiaryId) return "recipient"
  if (search.step === "recipient") return "recipient"
  if (search.step === "review" && amountIsValid) return "review"
  return "amount"
}

export function stepNumber(step: SendStep): number {
  return SEND_STEPS.findIndex((candidate) => candidate.key === step) + 1
}

/** Strip anything that can't be part of a rand amount, keeping 2 dp. */
export function sanitizeAmountInput(value: string): string {
  const cleaned = value.replace(/[^\d.]/g, "")
  const dot = cleaned.indexOf(".")
  if (dot === -1) return cleaned
  const whole = cleaned.slice(0, dot)
  const fraction = cleaned
    .slice(dot + 1)
    .replace(/\./g, "")
    .slice(0, 2)
  return `${whole}.${fraction}`
}

/** Rand, with at most two decimal places. */
const AMOUNT_PATTERN = /^\d+(\.\d{0,2})?$/

export type AmountIssue =
  | "empty"
  | "invalid"
  | "zero"
  | "too_small_for_fees"
  | "over_balance"
  | "over_daily_limit"
  | "over_monthly_limit"

export type AmountLimits = {
  /** The ZAR account's available balance, a 2 dp decimal string. */
  available?: string
  /** What's left to send today and this month, in ZAR. */
  dailyRemaining?: string
  monthlyRemaining?: string
}

/**
 * The first rule the amount breaks, in the order the ticket lists them.
 * Fees aren't known until the API prices the amount, so "too small to cover
 * the fees" comes from the preview's refusal (`isTooSmallForFees`) instead.
 * A limit that hasn't loaded yet isn't checked; the API still is.
 */
export function amountIssue(
  amount: string,
  limits: AmountLimits
): AmountIssue | null {
  if (!amount.trim()) return "empty"
  if (!AMOUNT_PATTERN.test(amount.trim())) return "invalid"
  // Comparing is all the UI does with an amount, and two-decimal values
  // compare exactly as numbers. The API does the money arithmetic.
  const value = Number(amount)
  if (value <= 0) return "zero"
  const over = (limit: string | undefined) =>
    limit !== undefined && value > Number(limit)
  if (over(limits.available)) return "over_balance"
  if (over(limits.dailyRemaining)) return "over_daily_limit"
  if (over(limits.monthlyRemaining)) return "over_monthly_limit"
  return null
}

/**
 * Only a well-formed, positive amount is worth pricing. Balance and limits
 * don't stop the preview: with an empty balance the sender can still see
 * what an amount would cost before adding money.
 */
export function canPreview(issue: AmountIssue | null): boolean {
  return (
    issue === null ||
    issue === "over_balance" ||
    issue === "over_daily_limit" ||
    issue === "over_monthly_limit"
  )
}

export function amountIssueMessage(
  issue: AmountIssue,
  limits: AmountLimits
): string {
  const zar = (value: string | undefined) =>
    formatMoney(value ?? "0", SENDER_CURRENCY)
  switch (issue) {
    case "empty":
      return "Enter an amount to send."
    case "invalid":
      return "Enter an amount in rand, like 500 or 500.50."
    case "zero":
      return "Enter an amount more than R 0.00."
    case "too_small_for_fees":
      return "That's too small to cover the fees. Try a larger amount."
    case "over_balance":
      return `That's more than your available balance of ${zar(limits.available)}.`
    case "over_daily_limit":
      return `That would exceed your daily limit. You can send up to ${zar(limits.dailyRemaining)} today.`
    case "over_monthly_limit":
      return `That would exceed your monthly limit. You can send up to ${zar(limits.monthlyRemaining)} this month.`
  }
}

/** The API's refusal for an amount the fees would swallow. */
export function isTooSmallForFees(error: unknown): boolean {
  return (
    error instanceof Error &&
    "status" in error &&
    error.status === 400 &&
    /too small to cover fees/i.test(error.message)
  )
}

/** The API answers 503 when no exchange rate is available. */
export function isRatesUnavailable(error: unknown): boolean {
  return error instanceof Error && "status" in error && error.status === 503
}

export const RATES_UNAVAILABLE_MESSAGE =
  "Exchange rates are unavailable right now."

/** One line of the quote the sender confirms. */
export type QuoteLine = {
  label: string
  value: string
  /** A second reading of the same line, e.g. the other exchange rate. */
  detail?: string
}

/**
 * The brief's quotation lines, in its order, with the amount converted
 * between the FX margin and the exchange rate. Every figure is the API's;
 * the fee rates are config there, so no label carries a percentage.
 */
export function quoteLines(quote: Quote): QuoteLine[] {
  const sender = quote.sender_currency
  const receiver = quote.receiver_currency
  return [
    { label: "You send", value: formatMoney(quote.sender_amount, sender) },
    {
      label: "Transfer fee",
      value: formatMoney(quote.sender_transaction_fee, sender),
    },
    {
      label: "FX margin",
      value: formatMoney(quote.exchange_rate_margin, sender),
    },
    {
      label: "Amount converted",
      value: formatMoney(quote.amount_converted, sender),
    },
    {
      label: "Exchange rate",
      value: `1 USD = R ${formatRate(quote.token_to_fiat_exchange_rate)}`,
      detail: `1 ${sender} = ${formatRate(quote.fiat_exchange_rate)} ${receiver}`,
    },
    {
      label: `${SETTLEMENT_TOKEN_LABEL} sent`,
      value: formatMoney(quote.token_amount, quote.token_name),
    },
    {
      label: "Cash-out fee",
      value: formatMoney(quote.receiver_payout_fee, receiver),
    },
    {
      label: "Recipient gets",
      value: formatMoney(quote.receiver_payout_estimate, receiver),
    },
  ]
}

/** Whole seconds left until `expiresAt`, never below zero. */
export function secondsLeft(expiresAt: string, now: number): number {
  return Math.max(0, Math.ceil((Date.parse(expiresAt) - now) / 1000))
}

/** 872 → "14:32". */
export function formatCountdown(seconds: number): string {
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`
}

function statusOf(error: unknown): number | undefined {
  return error instanceof Error && "status" in error
    ? (error.status as number)
    : undefined
}

export type QuoteRefusal = "rates_unavailable" | "unverified" | "other"

/** Why `createQuote` refused. Anything else shows the API's own detail. */
export function quoteRefusal(error: unknown): QuoteRefusal {
  const status = statusOf(error)
  if (status === 503) return "rates_unavailable"
  if (status === 403) return "unverified"
  return "other"
}

export type ConfirmRefusal =
  "quote_inactive" | "insufficient_balance" | "unverified" | "other"

/** Why `confirmRemittance` refused. */
export function confirmRefusal(error: unknown): ConfirmRefusal {
  const status = statusOf(error)
  if (status === 409) return "quote_inactive"
  if (status === 403) return "unverified"
  if (
    status === 400 &&
    error instanceof Error &&
    /available balance/i.test(error.message)
  ) {
    return "insufficient_balance"
  }
  return "other"
}
