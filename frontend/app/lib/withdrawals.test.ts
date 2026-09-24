import { describe, expect, it } from "vitest"

import type { AccountRead } from "~/client"
import {
  bankAccountLabel,
  bankAccountStatus,
  canWithdrawFrom,
  withdrawalAmountError,
  withdrawalStatus,
  withdrawHref,
} from "~/lib/withdrawals"

describe("withdrawalAmountError", () => {
  it.each([
    ["100", "1000.00"],
    ["0.01", "1000.00"],
    ["1000", "1000.00"],
    // A stored balance can carry trailing zeros.
    ["999.99", "1000.00000000"],
  ])("lets %s through against %s", (amount, available) => {
    expect(withdrawalAmountError(amount, available)).toBeNull()
  })

  it.each([
    ["", "Enter an amount."],
    ["   ", "Enter an amount."],
    ["1.234", "Enter an amount with up to two decimal places."],
    ["-5", "Enter an amount with up to two decimal places."],
    ["abc", "Enter an amount with up to two decimal places."],
    ["0", "Enter an amount above zero."],
    ["0.00", "Enter an amount above zero."],
    ["1000.01", "That's more than your available balance."],
  ])("refuses %j", (amount, message) => {
    expect(withdrawalAmountError(amount, "1000.00")).toBe(message)
  })
})

describe("canWithdrawFrom", () => {
  const account = (kind: AccountRead["kind"]) => ({ kind }) as AccountRead

  it("allows fiat accounts only", () => {
    expect(canWithdrawFrom(account("fiat"))).toBe(true)
    expect(canWithdrawFrom(account("settlement"))).toBe(false)
  })
})

describe("labels", () => {
  it("names a bank account by bank and number", () => {
    expect(
      bankAccountLabel({ bank_name: "FNB", account_number: "****7890" })
    ).toBe("FNB ****7890")
  })

  it("reads each verification status", () => {
    expect(bankAccountStatus("pending_verification").label).toBe(
      "Awaiting verification"
    )
    expect(bankAccountStatus("verified").variant).toBe("default")
    expect(bankAccountStatus("rejected").variant).toBe("destructive")
    expect(bankAccountStatus("something_new").label).toBe("something_new")
  })

  it("reads a settled withdrawal as paid out", () => {
    expect(withdrawalStatus("confirmed").label).toBe("Paid out")
    expect(withdrawalStatus("failed").variant).toBe("destructive")
  })

  it("links to the Withdraw page for a currency", () => {
    expect(withdrawHref("ZAR")).toBe("/app/withdraw?currency=ZAR")
  })
})
