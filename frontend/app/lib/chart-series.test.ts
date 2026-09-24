import { describe, expect, it } from "vitest"

import { lastDays, usedShare } from "~/lib/chart-series"

describe("usedShare", () => {
  it("is the fraction of the allowance already sent", () => {
    expect(usedShare("1100.00", "3000.00")).toBeCloseTo(1100 / 3000)
  })

  it("caps a send that is over the allowance", () => {
    expect(usedShare("4000.00", "3000.00")).toBe(1)
  })

  it("is zero when there is no allowance or nothing sent", () => {
    expect(usedShare("0.00", "0.00")).toBe(0)
    expect(usedShare("0.00", "3000.00")).toBe(0)
  })
})

describe("lastDays", () => {
  it("keeps the newest days of an oldest-first series", () => {
    expect(lastDays(["a", "b", "c", "d"], 2)).toEqual(["c", "d"])
  })

  it("returns the whole series when it is shorter than the window", () => {
    expect(lastDays(["a"], 7)).toEqual(["a"])
  })
})
