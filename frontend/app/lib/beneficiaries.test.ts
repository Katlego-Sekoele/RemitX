import { describe, expect, it } from "vitest"

import type { BeneficiaryRead } from "~/client"
import { quickPicks } from "~/lib/beneficiaries"

const beneficiary = (id: string) => ({ beneficiary_id: id }) as BeneficiaryRead
const list = ["a", "b", "c", "d"].map(beneficiary)
const ids = (picks: BeneficiaryRead[]) =>
  picks.map((pick) => pick.beneficiary_id)

describe("quickPicks", () => {
  it("offers the first few in list order", () => {
    expect(ids(quickPicks(list, null, 3))).toEqual(["a", "b", "c"])
  })

  it("never reorders the row when one of them is picked", () => {
    expect(ids(quickPicks(list, "b", 3))).toEqual(["a", "b", "c"])
  })

  it("gives the last slot to one picked from further down", () => {
    expect(ids(quickPicks(list, "d", 3))).toEqual(["a", "b", "d"])
  })

  it("ignores an id that isn't in the list", () => {
    expect(ids(quickPicks(list, "zz", 2))).toEqual(["a", "b"])
  })
})
