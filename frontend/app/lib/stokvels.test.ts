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

test("payoutStage follows release then remittance status", async () => {
  const { payoutStage } = await import("./stokvels")
  const none = { release_status: null, remittance_status: null }
  assert.equal(payoutStage(none, false), "collecting")
  assert.equal(payoutStage(none, true), "released")
  assert.equal(
    payoutStage({ release_status: "released", remittance_status: null }, true),
    "released"
  )
  assert.equal(
    payoutStage(
      { release_status: "released", remittance_status: "processing" },
      true
    ),
    "sending"
  )
  assert.equal(
    payoutStage(
      { release_status: "released", remittance_status: "confirmed" },
      true
    ),
    "delivered"
  )
  assert.equal(
    payoutStage(
      { release_status: "released", remittance_status: "failed" },
      true
    ),
    "failed"
  )
  // A failed pool release never reaches a remittance.
  assert.equal(
    payoutStage({ release_status: "failed", remittance_status: null }, true),
    "failed"
  )
})

test("a hash is proof only once confirmed", async () => {
  const { contributionProofHash, payoutProofHash } = await import("./stokvels")
  const hash = `0x${"a".repeat(64)}`
  assert.equal(
    contributionProofHash({ status: "pending", evm_tx_hash: hash }),
    null
  )
  assert.equal(
    contributionProofHash({ status: "processing", evm_tx_hash: hash }),
    null
  )
  assert.equal(
    contributionProofHash({ status: "confirmed", evm_tx_hash: hash }),
    hash
  )
  const round = {
    release_tx_hash: hash,
    burn_tx_hash: null,
    remittance_status: null,
  }
  assert.equal(
    payoutProofHash({ ...round, release_status: "processing" }),
    null
  )
  assert.equal(payoutProofHash({ ...round, release_status: "failed" }), null)
  assert.equal(payoutProofHash({ ...round, release_status: "released" }), hash)
  // A burn hash is stored before the burn is sent: proof only once the
  // payout is confirmed; until then the release's hash stands.
  const burn = `0x${"b".repeat(64)}`
  const burning = {
    ...round,
    release_status: "released" as const,
    burn_tx_hash: burn,
  }
  assert.equal(
    payoutProofHash({ ...burning, remittance_status: "processing" }),
    hash
  )
  assert.equal(
    payoutProofHash({ ...burning, remittance_status: "confirmed" }),
    burn
  )
})

test("contributeMock pays once, confirms, and refuses the doc §6 cases", async () => {
  const { contributeMock, resetStokvelMockScenario, stokvelMockScenario } =
    await import("./stokvels.mock")
  const { outstandingMembers } = await import("./stokvels")
  resetStokvelMockScenario()
  stokvelMockScenario.confirm_delay_ms = 1

  stokvelMockScenario.paused = true
  await expect(contributeMock("stk_8c21")).rejects.toMatchObject({
    status: 503,
    body: { code: "stokvel_paused" },
  })
  stokvelMockScenario.paused = false

  await expect(contributeMock("stk_77e0")).rejects.toMatchObject({
    body: { code: "cycle_not_open" },
  })

  // Covers the R500 contribution but not the R7.50 fee share on top.
  stokvelMockScenario.available_balance = "505.00"
  await expect(contributeMock("stk_8c21")).rejects.toThrow(
    /available ZAR balance is 505.00, and this contribution needs 507.50/
  )
  stokvelMockScenario.available_balance = "1240.00"

  const before = await getStokvelMock("stk_8c21")
  assert.equal(outstandingMembers(before).length, 1)
  const paid = await contributeMock("stk_8c21")
  assert.equal(paid.status, "confirmed")
  // R15 + 0.5% of the R1,500 pool = R22.50, split over 3 members.
  assert.equal(paid.fee_amount, "7.50")
  assert.equal(paid.amount_zar, "507.50")
  const after = await getStokvelMock("stk_8c21")
  assert.equal(outstandingMembers(after).length, 0)
  assert.equal(after.my_contribution_status, "confirmed")
  assert.equal(stokvelMockScenario.available_balance, "732.50")
  const mine = after.contributions.find(
    (c) => c.member_id === after.my_member_id && c.round === 1
  )
  assert.match(mine?.evm_tx_hash ?? "", /^0x[0-9a-z]{64}$/)

  await expect(contributeMock("stk_8c21")).rejects.toMatchObject({
    status: 409,
    body: { code: "contribution_already_paid" },
  })
  resetStokvelMockScenario()
})
