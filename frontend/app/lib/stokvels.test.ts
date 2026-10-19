import { assert, expect, test } from "vitest"

import { demoStokvelsMock, getStokvelMock } from "./stokvels.mock"
import {
  currentRecipientId,
  explorerTxUrl,
  feeShare,
  fiatToToken,
  isDemoStokvel,
  paidMemberIds,
  poolAmount,
  roundLabel,
  stokvelPath,
  tokenToFiat,
} from "./stokvels"

test("roundLabel shows the round 1-based", () => {
  assert.equal(roundLabel(0, 3), "Round 1 of 3")
  assert.equal(roundLabel(2, 3), "Round 3 of 3")
})

test("poolAmount multiplies the contribution by the member count", () => {
  assert.equal(poolAmount("500.00", 3), "1500.00")
  assert.equal(poolAmount("0.01", 3), "0.03")
})

test("paidMemberIds counts only confirmed contributions to the round", async () => {
  const detail = await getStokvelMock("stk_8c21")
  const paid = paidMemberIds(detail)
  assert.deepEqual([...paid].sort(), ["mem_lerato", "mem_thabo"])
  assert.equal(paidMemberIds(detail, 0).size, 3)
  assert.equal(paidMemberIds({ cycle: null, contributions: [] }).size, 0)
})

test("currentRecipientId follows the payout order of an active cycle", async () => {
  const detail = await getStokvelMock("stk_8c21")
  assert.equal(currentRecipientId(detail.cycle), "mem_sipho")
  assert.equal(currentRecipientId(null), null)
  const closed = await getStokvelMock("stk_02bd")
  assert.equal(currentRecipientId(closed.cycle), null)
})

test("demo list rows carry exactly the generated StokvelRead fields", async () => {
  const list = await demoStokvelsMock()
  assert.equal(list.stokvels.length, 3)
  for (const row of list.stokvels) {
    assert.deepEqual(Object.keys(row).sort(), [
      "contribution_amount",
      "created_at",
      "currency",
      "deactivated_at",
      "is_organiser",
      "max_members",
      "member_count",
      "name",
      "stokvel_id",
    ])
  }
  assert.equal(list.invitations.length, 1)
  assert.equal(list.invitations[0].invited_by_name, "Naledi M.")
})

test("fiatToToken and tokenToFiat convert exactly, rounding half up", () => {
  const rate = "0.05479452"
  assert.equal(fiatToToken("500.00", rate), "27.39726000")
  assert.equal(fiatToToken("300", rate), "16.43835600")
  assert.equal(fiatToToken("1", "0.000000005"), "0.00000001")
  // The create body's precision: whole cents of UCTUSD.
  assert.equal(fiatToToken("500.00", rate, 2), "27.40")
  assert.equal(fiatToToken("10", rate, 2), "0.55")
  assert.equal(tokenToFiat("27.40000000", rate), "500.05")
  assert.equal(tokenToFiat("13.70000000", rate), "250.03")
  assert.equal(tokenToFiat("27.39726000", rate), "500.00")
  assert.equal(tokenToFiat("0.005", "1"), "0.01")
  assert.throws(() => tokenToFiat("1", "0"), /zero rate/)
  assert.throws(() => fiatToToken("-1", rate), /non-negative/)
})

test("mock detail rejects an unknown id", async () => {
  await expect(getStokvelMock("stk_nope")).rejects.toThrow("Stokvel not found")
})

test("paths and explorer links", () => {
  assert.equal(stokvelPath("stk_8c21"), "/app/stokvels/stk_8c21")
  assert.match(explorerTxUrl("0xabc"), /\/tx\/0xabc$/)
})

test("feeShare splits fee and margin evenly, rounding up to the cent", () => {
  // R15 + 0.5% of R1,500 = R22.50, no margin in the same currency.
  assert.equal(feeShare("22.50", "0", 3), "7.50")
  // R22.50 fee + R15.00 margin = R37.50 over 3.
  assert.equal(feeShare("22.50000000", "15.00000000", 3), "12.50")
  // R10.00 over 3 rounds up, so the members always cover the fee.
  assert.equal(feeShare("10.00", "0.00", 3), "3.34")
  assert.equal(feeShare("0.00000001", "0", 1), "0.01")
  assert.throws(() => feeShare("1", "0", 0), /members/)
})

test("demo ids are the mock's, real ids are UUIDs", () => {
  assert.equal(isDemoStokvel("stk_8c21"), true)
  assert.equal(isDemoStokvel("4f1c2b7e-0d1a-4c55-9a8e-2b7a1f0c9d33"), false)
})
