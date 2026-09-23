import { describe, expect, it } from "vitest"

import { currencyLabel, formatMoney, formatRate } from "~/lib/money"

// Intl may separate the symbol with a no-break space; compare on plain ones.
const plain = (value: string) => value.replace(/\s/g, " ")

describe("formatMoney", () => {
  it("formats rand with its symbol and other currencies by code", () => {
    expect(plain(formatMoney("1000.00", "ZAR"))).toBe("R 1,000.00")
    expect(plain(formatMoney("1354.37", "ZWL"))).toBe("ZWL 1,354.37")
    expect(plain(formatMoney("5", "NAD"))).toBe("NAD 5.00")
    expect(plain(formatMoney("5", "USD"))).toBe("USD 5.00")
  })

  it("calls the token RLUSD", () => {
    expect(plain(formatMoney("52.43", "uctusd"))).toBe("RLUSD 52.43")
    expect(currencyLabel("uctusd")).toBe("RLUSD")
  })

  it("keeps digits a float would drop", () => {
    expect(plain(formatMoney("12345678901234567.89", "ZAR"))).toBe(
      "R 12,345,678,901,234,567.89"
    )
  })
})

describe("formatRate", () => {
  it("displays to 4 dp", () => {
    expect(formatRate("16.22")).toBe("16.2200")
    expect(formatRate("18.50000185")).toBe("18.5000")
  })
})
