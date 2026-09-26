import { describe, expect, it } from "vitest"

import type { QuoteRead } from "~/client"
import { ApiError } from "~/lib/api"
import {
  amountIssue,
  amountIssueMessage,
  canPreview,
  confirmRefusal,
  formatCountdown,
  quoteLines,
  quoteRefusal,
  secondsLeft,
  isRatesUnavailable,
  isTooSmallForFees,
  readSendSearch,
  resolveStep,
  sanitizeAmountInput,
  stepNumber,
  writeSendSearch,
  type AmountIssue,
} from "~/lib/send"

const plain = (value: string) => value.replace(/\s/g, " ")

describe("search params", () => {
  it("reads what the URL holds", () => {
    const search = readSendSearch(
      new URLSearchParams("beneficiary=b1&amount=250&currency=NAD&step=review")
    )
    expect(search).toEqual({
      beneficiaryId: "b1",
      amount: "250",
      currency: "NAD",
      step: "review",
    })
  })

  it("ignores a currency or step it doesn't know", () => {
    const search = readSendSearch(new URLSearchParams("currency=EUR&step=sent"))
    expect(search.currency).toBeNull()
    expect(search.step).toBeNull()
  })

  it("round-trips, dropping empty values", () => {
    const current = readSendSearch(new URLSearchParams("beneficiary=b1"))
    const next = writeSendSearch(current, { amount: "", step: "amount" })
    expect(next.toString()).toBe("beneficiary=b1&step=amount")
    expect(readSendSearch(next)).toEqual({ ...current, step: "amount" })
  })
})

describe("resolveStep", () => {
  const base = readSendSearch(new URLSearchParams())

  it("starts at Recipient", () => {
    expect(resolveStep(base, false)).toBe("recipient")
  })

  it("skips to Amount when a beneficiary is preselected", () => {
    expect(resolveStep({ ...base, beneficiaryId: "b1" }, false)).toBe("amount")
  })

  it("lets the sender go back to Recipient without losing the choice", () => {
    expect(
      resolveStep({ ...base, beneficiaryId: "b1", step: "recipient" }, true)
    ).toBe("recipient")
  })

  it("only reaches Review with a valid amount", () => {
    const review = { ...base, beneficiaryId: "b1", step: "review" as const }
    expect(resolveStep(review, false)).toBe("amount")
    expect(resolveStep(review, true)).toBe("review")
  })

  it("numbers the steps from 1", () => {
    expect(stepNumber("recipient")).toBe(1)
    expect(stepNumber("review")).toBe(3)
    expect(stepNumber("sent")).toBe(4)
  })
})

describe("sanitizeAmountInput", () => {
  it.each([
    ["R 1,000.505", "1000.50"],
    ["12.3.4", "12.34"],
    ["abc", ""],
    ["250", "250"],
  ])("%s → %s", (typed, kept) => {
    expect(sanitizeAmountInput(typed)).toBe(kept)
  })
})

describe("amountIssue", () => {
  const limits = {
    available: "1000.00",
    dailyRemaining: "800.00",
    monthlyRemaining: "600.00",
  }

  it.each<[string, AmountIssue | null]>([
    ["", "empty"],
    ["1.234", "invalid"],
    ["0", "zero"],
    ["0.00", "zero"],
    // Too large beats over-balance: it's the reason the preview won't run.
    ["1000000000000", "too_large"],
    ["1" + "0".repeat(27), "too_large"],
    ["1000.01", "over_balance"],
    ["800.01", "over_daily_limit"],
    ["600.01", "over_monthly_limit"],
    ["600.00", null],
    ["0.01", null],
  ])("%s → %s", (amount, issue) => {
    expect(amountIssue(amount, limits)).toBe(issue)
  })

  it("skips a limit that hasn't loaded", () => {
    expect(amountIssue("5000", {})).toBeNull()
  })

  it("allows up to the largest amount the ledger holds", () => {
    expect(amountIssue("999999999999.99", {})).toBeNull()
    expect(amountIssue("1000000000000.00", {})).toBe("too_large")
  })

  it("doesn't preview an amount too large to price", () => {
    expect(canPreview(amountIssue("1000000000000", limits))).toBe(false)
  })

  it("gives every issue its own message", () => {
    const issues: AmountIssue[] = [
      "empty",
      "invalid",
      "zero",
      "too_large",
      "too_small_for_fees",
      "over_balance",
      "over_daily_limit",
      "over_monthly_limit",
    ]
    const messages = issues.map((issue) => amountIssueMessage(issue, limits))
    expect(new Set(messages).size).toBe(issues.length)
    expect(plain(amountIssueMessage("over_daily_limit", limits))).toContain(
      "R 800.00 today"
    )
  })

  it("previews amounts that only break the balance or a limit", () => {
    expect(canPreview(null)).toBe(true)
    expect(canPreview("over_balance")).toBe(true)
    expect(canPreview("over_monthly_limit")).toBe(true)
    expect(canPreview("zero")).toBe(false)
    expect(canPreview("invalid")).toBe(false)
  })
})

describe("API refusals", () => {
  it("recognises the fees refusal", () => {
    const error = new ApiError("sender_amount is too small to cover fees", 400)
    expect(isTooSmallForFees(error)).toBe(true)
    expect(isTooSmallForFees(new ApiError("Beneficiary not found", 400))).toBe(
      false
    )
  })

  it("recognises missing rates", () => {
    expect(
      isRatesUnavailable(new ApiError("Exchange rate unavailable", 503))
    ).toBe(true)
    expect(isRatesUnavailable(new Error("boom"))).toBe(false)
  })
})

const QUOTE: QuoteRead = {
  quote_id: "q1",
  sender_user_id: "u1",
  beneficiary_user_id: "u2",
  sender_amount: "1000.00",
  sender_currency: "ZAR",
  sender_transaction_fee: "20.00",
  exchange_rate_margin: "10.00",
  fiat_to_token_exchange_rate: "0.05405405",
  fiat_exchange_rate: "16.22000000",
  token_amount: "52.43",
  token_name: "uctusd",
  receiver_amount: "15733.40",
  receiver_currency: "ZWL",
  receiver_payout_fee: "118.00",
  receiver_payout_estimate: "15615.40",
  created_at: "2026-09-22T10:00:00+00:00",
  expires_at: "2026-09-22T10:15:00+00:00",
  status: "active",
}

describe("quoteLines", () => {
  const lines = quoteLines(QUOTE).map((line) => ({
    ...line,
    value: plain(line.value),
    detail: line.detail && plain(line.detail),
  }))

  it("lists the brief's lines in order, with the amount converted", () => {
    expect(lines.map((line) => line.label)).toEqual([
      "You send",
      "Transfer fee",
      "FX margin",
      "Amount converted",
      "Exchange rate",
      "RLUSD sent",
      "Recipient gets",
      "Recipient cash-out fee",
      "Estimated payout if recipient withdraws",
    ])
  })

  it("formats every value from the quote", () => {
    expect(lines.map((line) => line.value)).toEqual([
      "R 1,000.00",
      "R 20.00",
      "R 10.00",
      "R 970.00",
      "1 RLUSD = R 18.5000",
      "RLUSD 52.43",
      "ZWL 15,733.40",
      "ZWL 118.00",
      "ZWL 15,615.40",
    ])
    expect(lines[4].detail).toBe("1 ZAR = 16.2200 ZWL")
  })

  it("keeps percentages out of the labels", () => {
    expect(lines.some((line) => line.label.includes("%"))).toBe(false)
  })

  it("shows a zero FX margin on a same-currency send", () => {
    const sameCurrency = quoteLines({
      ...QUOTE,
      exchange_rate_margin: "0E-8",
      fiat_exchange_rate: "1.00000000",
      receiver_currency: "ZAR",
    }).map((line) => ({ label: line.label, value: plain(line.value) }))

    expect(sameCurrency).toContainEqual({ label: "FX margin", value: "R 0.00" })
    expect(sameCurrency).toContainEqual({
      label: "Amount converted",
      value: "R 980.00",
    })
  })

  it("hides the sender's fees on a received transfer", () => {
    const received = quoteLines({
      ...QUOTE,
      sender_amount: null,
      sender_transaction_fee: null,
      exchange_rate_margin: null,
    }).map((line) => line.label)

    expect(received).toEqual([
      "Exchange rate",
      "RLUSD sent",
      "Received",
      "Recipient cash-out fee",
      "Estimated payout if recipient withdraws",
    ])
  })
})

describe("countdown", () => {
  const expires = Date.parse(QUOTE.expires_at)

  it("counts whole seconds down to zero", () => {
    expect(secondsLeft(QUOTE.expires_at, expires - 15 * 60 * 1000)).toBe(900)
    expect(secondsLeft(QUOTE.expires_at, expires - 1500)).toBe(2)
    expect(secondsLeft(QUOTE.expires_at, expires)).toBe(0)
    expect(secondsLeft(QUOTE.expires_at, expires + 60_000)).toBe(0)
  })

  it("reads as minutes and seconds", () => {
    expect(formatCountdown(872)).toBe("14:32")
    expect(formatCountdown(900)).toBe("15:00")
    expect(formatCountdown(5)).toBe("0:05")
  })
})

describe("refusals", () => {
  it("classifies a quote refusal", () => {
    expect(quoteRefusal(new ApiError("Exchange rate unavailable", 503))).toBe(
      "rates_unavailable"
    )
    expect(quoteRefusal(new ApiError("Only KYC-approved users", 403))).toBe(
      "unverified"
    )
    expect(quoteRefusal(new ApiError("Beneficiary not found", 400))).toBe(
      "other"
    )
  })

  it("classifies a confirm refusal", () => {
    expect(confirmRefusal(new ApiError("Quote is no longer active", 409))).toBe(
      "quote_inactive"
    )
    expect(
      confirmRefusal(
        new ApiError("available balance 10.00 is less than 1000.00", 400)
      )
    ).toBe("insufficient_balance")
    expect(confirmRefusal(new ApiError("Verification lapsed", 403))).toBe(
      "unverified"
    )
    expect(confirmRefusal(new ApiError("Quote not found", 400))).toBe("other")
  })

  it("classifies a confirm the sending limits refused", () => {
    expect(
      confirmRefusal(
        new ApiError(
          "This would exceed your daily limit. You can send up to R 1,000.00 today.",
          400
        )
      )
    ).toBe("over_limit")
    expect(
      confirmRefusal(
        new ApiError(
          "You've reached your monthly limit. You can send again next month.",
          400
        )
      )
    ).toBe("over_limit")
  })
})
