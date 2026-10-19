import { assert, beforeEach, expect, test } from "vitest"

import { pauseReasonIssue } from "./stokvel-contract"
import {
  getStokvelContractMock,
  pauseStokvelContractMock,
  resetStokvelContractMock,
  resumeStokvelContractMock,
} from "./stokvel-contract.mock"

beforeEach(() => resetStokvelContractMock())

test("a pause needs a reason worth reading in the audit log", () => {
  assert.match(pauseReasonIssue("   ") ?? "", /Give a reason/)
  assert.match(pauseReasonIssue("bug") ?? "", /at least 10/)
  assert.equal(pauseReasonIssue("Investigating a failed payout"), null)
  assert.match(pauseReasonIssue("x".repeat(501)) ?? "", /500 characters/)
})

test("pause records when and why; resume clears both", async () => {
  const before = await getStokvelContractMock()
  assert.equal(before.paused, false)

  const paused = await pauseStokvelContractMock({
    reason: "  Investigating a failed payout  ",
  })
  assert.equal(paused.paused, true)
  assert.equal(paused.paused_reason, "Investigating a failed payout")
  assert.ok(paused.paused_at)
  assert.equal((await getStokvelContractMock()).paused, true)

  await expect(
    pauseStokvelContractMock({ reason: "Again, by mistake" })
  ).rejects.toMatchObject({ status: 409, body: { code: "stokvel_paused" } })

  const resumed = await resumeStokvelContractMock()
  assert.equal(resumed.paused, false)
  assert.equal(resumed.paused_at, null)
  assert.equal(resumed.paused_reason, null)
  await expect(resumeStokvelContractMock()).rejects.toMatchObject({
    status: 409,
  })
})

test("the mock refuses a pause without a reason, like the API", async () => {
  await expect(pauseStokvelContractMock({ reason: " " })).rejects.toMatchObject(
    { status: 422 }
  )
})
