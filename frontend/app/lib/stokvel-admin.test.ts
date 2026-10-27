import { assert, beforeEach, expect, test } from "vitest"

import {
  canReleaseByHand,
  finaliseHint,
  finaliseRefusalMessage,
} from "./stokvel-admin"
import {
  finaliseRoundMock,
  listAdminRoundsMock,
  resetAdminRoundsMock,
} from "./stokvel-admin.mock"

beforeEach(() => resetAdminRoundsMock())

const NOW = new Date("2026-10-19T12:00:00Z")
const ready = {
  paid_count: 3,
  member_count: 3,
  payout_time: "2026-10-18T12:00:00Z",
  release_status: "pending" as const,
  manual_release_allowed: true,
}

test("finaliseHint says why a round isn't ready, or nothing", () => {
  assert.equal(finaliseHint(ready, NOW), null)
  assert.equal(
    finaliseHint({ ...ready, paid_count: 2 }, NOW),
    "Waiting for 1 member to pay."
  )
  assert.equal(
    finaliseHint({ ...ready, paid_count: 1 }, NOW),
    "Waiting for 2 members to pay."
  )
  assert.equal(
    finaliseHint({ ...ready, payout_time: "2026-10-20T12:00:00Z" }, NOW),
    "Its payout time hasn't come yet."
  )
  assert.equal(
    finaliseHint({ ...ready, release_status: "released" }, NOW),
    "Already paid out."
  )
})

test("refusals show the doc §6 wording, others the API's message", () => {
  const refused = (code: string) =>
    Object.assign(new Error("raw"), { body: { code, detail: "raw" } })
  assert.equal(
    finaliseRefusalMessage(refused("round_not_finalisable")),
    "This round can't be paid out yet."
  )
  assert.equal(
    finaliseRefusalMessage(refused("round_already_finalised")),
    "This round has already been paid out."
  )
  assert.equal(
    finaliseRefusalMessage(refused("round_release_not_pending")),
    "This round's payout is already in progress or has failed, so it can't be queued again."
  )
  assert.equal(
    finaliseRefusalMessage(refused("stokvel_chain_mismatch")),
    "This stokvel's records don't match the contract. An operator needs to check the vault before this round can be paid out."
  )
  assert.equal(
    finaliseRefusalMessage(
      Object.assign(new Error("Server error"), { body: { detail: "x" } })
    ),
    "Server error"
  )
  assert.equal(
    finaliseRefusalMessage(undefined),
    "Something went wrong. Please try again."
  )
})

test("the mock releases a ready round and refuses the rest like the contract", async () => {
  const rounds = await listAdminRoundsMock()
  const byName = (name: string) => rounds.find((r) => r.stokvel_name === name)!

  const stalled = byName("December groceries")
  const released = await finaliseRoundMock(stalled.stokvel_id, stalled.round)
  assert.equal(released.release_status, "released")
  assert.match(released.release_tx_hash ?? "", /^0x[0-9a-f]{64}$/)
  await expect(
    finaliseRoundMock(stalled.stokvel_id, stalled.round)
  ).rejects.toMatchObject({
    status: 409,
    body: { code: "round_already_finalised" },
  })

  for (const name of ["Burial society", "Taxi fund"]) {
    const row = byName(name)
    await expect(
      finaliseRoundMock(row.stokvel_id, row.round)
    ).rejects.toMatchObject({
      status: 409,
      body: { code: "round_not_finalisable" },
    })
  }
  await expect(finaliseRoundMock("stk_nope", 0)).rejects.toMatchObject({
    status: 404,
  })
})

test("the release button follows manual_release_allowed from the API", () => {
  const row = {
    ...ready,
    stokvel_id: "x",
    stokvel_name: "Club",
    round: 0,
    total_rounds: 3,
    recipient_name: "A",
    release_tx_hash: null,
    manual_release_allowed: true,
  }
  assert.equal(canReleaseByHand(row), true)
  assert.equal(
    canReleaseByHand({ ...row, manual_release_allowed: false }),
    false
  )
  assert.equal(
    finaliseHint({ ...ready, release_status: "processing" }, NOW),
    "Release in progress."
  )
  assert.equal(
    finaliseHint(
      {
        ...ready,
        paid_count: 3,
        manual_release_allowed: false,
      },
      NOW
    ),
    "Waiting for the next round to fill."
  )
})

test("the mock releases a failed round and refuses one in flight", async () => {
  const rounds = await listAdminRoundsMock()
  const failed = rounds.find((r) => r.release_status === "failed")!
  const inFlight = rounds.find((r) => r.release_status === "processing")!
  const released = await finaliseRoundMock(failed.stokvel_id, failed.round)
  assert.equal(released.release_status, "released")
  await expect(
    finaliseRoundMock(inFlight.stokvel_id, inFlight.round)
  ).rejects.toMatchObject({ status: 409 })
})
