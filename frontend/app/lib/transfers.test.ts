import { describe, expect, it } from "vitest"

import { TransactionStatus } from "~/client"
import {
  explorerUrl,
  headlineAmount,
  isInFlight,
  isSlowToStart,
  shortHash,
  statusCopy,
  transferPath,
} from "~/lib/transfers"

describe("status", () => {
  it("names each settlement status", () => {
    expect(statusCopy(TransactionStatus.PENDING).label).toBe("Queued")
    expect(statusCopy(TransactionStatus.PROCESSING).label).toBe(
      "Settling on XRPL"
    )
    expect(statusCopy(TransactionStatus.CONFIRMED).label).toBe("Completed")
    expect(statusCopy(TransactionStatus.FAILED).label).toBe("Failed")
    expect(statusCopy(TransactionStatus.FAILED).badge).toBe("destructive")
  })

  it("polls only while in flight", () => {
    expect(isInFlight(TransactionStatus.PENDING)).toBe(true)
    expect(isInFlight(TransactionStatus.PROCESSING)).toBe(true)
    expect(isInFlight(TransactionStatus.CONFIRMED)).toBe(false)
    expect(isInFlight(TransactionStatus.FAILED)).toBe(false)
  })
})

describe("isSlowToStart", () => {
  const created = "2026-09-22T10:00:00+00:00"
  const at = (seconds: number) => Date.parse(created) + seconds * 1000

  it("warns once queued for more than a minute", () => {
    expect(isSlowToStart(TransactionStatus.PENDING, created, at(59))).toBe(
      false
    )
    expect(isSlowToStart(TransactionStatus.PENDING, created, at(61))).toBe(true)
  })

  it("never warns once settlement has started", () => {
    expect(isSlowToStart(TransactionStatus.PROCESSING, created, at(600))).toBe(
      false
    )
  })
})

describe("hashes", () => {
  it("truncates to the first and last four", () => {
    expect(shortHash("A1B2C3D4E5F6A7B89F0E")).toBe("A1B2…9F0E")
  })

  it("links to the testnet explorer", () => {
    expect(explorerUrl("ABC")).toBe("https://testnet.xrpl.org/transactions/ABC")
  })
})

describe("headlineAmount", () => {
  const transfer = {
    sender_amount: "1000.00",
    sender_currency: "ZAR",
    receiver_amount: "15416.29",
    receiver_currency: "ZWL",
  }

  it("shows what was sent, to the sender", () => {
    expect(headlineAmount({ ...transfer, direction: "sent" })).toEqual({
      amount: "1000.00",
      currency: "ZAR",
    })
  })

  it("shows what was received, to the recipient", () => {
    expect(
      headlineAmount({
        ...transfer,
        direction: "received",
        sender_amount: null,
      })
    ).toEqual({ amount: "15416.29", currency: "ZWL" })
  })
})

it("builds a transfer's path", () => {
  expect(transferPath("r1")).toBe("/app/transfers/r1")
})
