import { describe, expect, it } from "vitest"

import { ApiError } from "~/lib/api"
import {
  amountIssue,
  amountIssueMessage,
  canPreview,
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

  it("gives every issue its own message", () => {
    const issues: AmountIssue[] = [
      "empty",
      "invalid",
      "zero",
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
