import { assert, expect, test } from "vitest"

import { getStokvelMock, listStokvelsMock } from "./stokvels.mock"
import {
  currentRecipientId,
  explorerTxUrl,
  paidMemberIds,
  poolAmount,
  roundLabel,
  stokvelPath,
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

test("mock list has one stokvel per phase and a pending invitation", async () => {
  const list = await listStokvelsMock()
  assert.deepEqual(list.stokvels.map((s) => s.phase).sort(), [
    "active",
    "closed",
    "forming",
  ])
  assert.equal(list.invitations.length, 1)
  assert.equal(list.invitations[0].status, "pending")
})

test("mock detail rejects an unknown id", async () => {
  await expect(getStokvelMock("stk_nope")).rejects.toThrow("Stokvel not found")
})

test("paths and explorer links", () => {
  assert.equal(stokvelPath("stk_8c21"), "/app/stokvels/stk_8c21")
  assert.match(explorerTxUrl("0xabc"), /\/tx\/0xabc$/)
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

  stokvelMockScenario.available_balance = "10.00"
  await expect(contributeMock("stk_8c21")).rejects.toThrow(/available balance/)
  stokvelMockScenario.available_balance = "1240.00"

  const before = await getStokvelMock("stk_8c21")
  assert.equal(outstandingMembers(before).length, 1)
  const paid = await contributeMock("stk_8c21")
  assert.equal(paid.status, "confirmed")
  assert.match(paid.evm_tx_hash ?? "", /^0x[0-9a-z]{64}$/)
  const after = await getStokvelMock("stk_8c21")
  assert.equal(outstandingMembers(after).length, 0)
  assert.equal(after.my_contribution_status, "confirmed")
  assert.equal(stokvelMockScenario.available_balance, "740.00")

  await expect(contributeMock("stk_8c21")).rejects.toMatchObject({
    status: 409,
    body: { code: "contribution_already_paid" },
  })
  resetStokvelMockScenario()
})
