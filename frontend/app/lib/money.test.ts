import { describe, expect, it } from "vitest"

import {
  amountToCents,
  currencyLabel,
  formatFiatToTokenExchangeRate,
  formatMoney,
  formatRate,
  fromCents,
  invertRate,
  subtractAmounts,
  toCents,
} from "~/lib/money"

// Intl may separate the symbol with a no-break space; compare on plain ones.
const plain = (value: string) => value.replace(/\s/g, " ")

describe("toCents", () => {
  it.each([
    ["1000", 100000n],
    ["1000.5", 100050n],
    ["1000.50", 100050n],
    ["0.01", 1n],
    ["12.", 1200n],
    [" 7 ", 700n],
  ])("reads %s", (value, cents) => {
    expect(toCents(value)).toBe(cents)
  })

  it.each(["", "abc", "1.234", "-5", "1,000", ".5", "1e3"])(
    "refuses %s",
    (value) => {
      expect(toCents(value)).toBeNull()
    }
  )
})

describe("fromCents", () => {
  it("writes two decimal places", () => {
    expect(fromCents(100050n)).toBe("1000.50")
    expect(fromCents(5n)).toBe("0.05")
    expect(fromCents(-150n)).toBe("-1.50")
  })
})

describe("amountToCents", () => {
  it("accepts trailing zeros past 2 dp", () => {
    expect(amountToCents("12.50000000")).toBe(1250n)
  })

  it("refuses a value that would lose a cent", () => {
    expect(() => amountToCents("12.505")).toThrow()
  })
})

describe("subtractAmounts", () => {
  it("is exact where floats are not", () => {
    // 0.3 - 0.1 - 0.1 is 0.09999999999999998 in floating point.
    expect(subtractAmounts("0.30", "0.10", "0.10")).toBe("0.10")
    expect(subtractAmounts("1000.00", "20.00", "10.00")).toBe("970.00")
  })
})

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

describe("rates", () => {
  it("displays to 4 dp", () => {
    expect(formatRate("16.22")).toBe("16.2200")
  })

  it("inverts the token rate into rand per dollar", () => {
    // 1 / 18.50 quantized to 8 dp by the API, then read back.
    expect(invertRate("0.05405405")).toBe("18.5000")
    expect(invertRate("0.5")).toBe("2.0000")
    expect(invertRate("1")).toBe("1.0000")
    expect(invertRate("3", 2)).toBe("0.33")
  })

  it("rounds half up", () => {
    // 1 / 8 = 0.125
    expect(invertRate("8", 2)).toBe("0.13")
  })

  it("labels the inverted token rate from the quote currencies", () => {
    expect(formatFiatToTokenExchangeRate("0.05405405", "ZAR", "uctusd")).toBe(
      "1 RLUSD = R 18.5000"
    )
    expect(formatFiatToTokenExchangeRate("1", "USD", "uctusd")).toBe(
      "1 RLUSD = USD 1.0000"
    )
  })
})
