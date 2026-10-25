import { assert, test } from "vitest"

import {
  explorerTxUrl,
  feeShare,
  fiatToToken,
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
  const { paidMemberIds } = await import("./stokvels")
  const detail = {
    cycle: { cycle_id: "c", current_round: 1 },
    contributions: [
      { cycle_id: "c", round: 1, member_id: "a", status: "confirmed" as const },
      { cycle_id: "c", round: 1, member_id: "b", status: "pending" as const },
      { cycle_id: "c", round: 0, member_id: "a", status: "confirmed" as const },
      { cycle_id: "c", round: 0, member_id: "b", status: "confirmed" as const },
      { cycle_id: "c", round: 0, member_id: "d", status: "confirmed" as const },
    ],
  }
  assert.deepEqual([...paidMemberIds(detail)].sort(), ["a"])
  assert.equal(paidMemberIds(detail, 0).size, 3)
  assert.equal(paidMemberIds({ cycle: null, contributions: [] }).size, 0)
})

test("currentRecipientId follows the payout order of an active cycle", async () => {
  const { currentRecipientId } = await import("./stokvels")
  assert.equal(
    currentRecipientId({
      status: "active",
      current_round: 1,
      payout_order: ["a", "b"],
    } as never),
    "b"
  )
  assert.equal(currentRecipientId(null), null)
  assert.equal(
    currentRecipientId({
      status: "closed",
      current_round: 0,
      payout_order: ["a"],
    } as never),
    null
  )
  assert.equal(
    currentRecipientId({
      status: "active",
      current_round: null,
      payout_order: ["a"],
    } as never),
    null
  )
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

test("openRound is the first round that is not full of non-failed rows", async () => {
  const { openRound } = await import("./stokvels")
  const cycle = {
    cycle_id: "cyc",
    status: "active" as const,
    total_rounds: 3,
    current_round: 0,
  }
  const row = (round: number, status: "confirmed" | "pending" | "failed") => ({
    cycle_id: "cyc",
    round,
    status,
  })
  const full = [0, 1, 2].map((i) => row(0, i === 2 ? "pending" : "confirmed"))
  assert.equal(openRound({ cycle, contributions: full }), 1)
  assert.equal(
    openRound({ cycle, contributions: [...full, row(0, "failed")] }),
    1
  )
  assert.equal(openRound({ cycle, contributions: [] }), 0)
  assert.equal(
    openRound({
      cycle,
      contributions: [0, 1, 2].flatMap((round) =>
        [0, 1, 2].map(() => row(round, "confirmed"))
      ),
    }),
    null
  )
  assert.equal(
    openRound({ cycle: { ...cycle, status: "forming" }, contributions: [] }),
    null
  )
  assert.equal(openRound({ cycle: null, contributions: [] }), null)
  assert.equal(
    openRound({
      cycle,
      contributions: [{ ...row(0, "confirmed"), cycle_id: "other" }],
    }),
    0
  )
})

test("myCurrentContribution skips a failed attempt for the live one", async () => {
  const { myCurrentContribution } = await import("./stokvels")
  const base = {
    contribution_id: "c",
    cycle_id: "cyc",
    round: 1,
    member_id: "me",
    amount_fiat: "500.00",
    amount_token: "27.40",
    fee_amount: "7.50",
    evm_tx_hash: null,
    created_at: "",
  }
  const detail = {
    my_member_id: "me",
    cycle: {
      cycle_id: "cyc",
      status: "active",
      total_rounds: 3,
      current_round: 0,
    } as never,
    contributions: [
      {
        ...base,
        round: 0,
        contribution_id: "r0a",
        member_id: "a",
        status: "confirmed" as const,
      },
      {
        ...base,
        round: 0,
        contribution_id: "r0b",
        member_id: "b",
        status: "confirmed" as const,
      },
      {
        ...base,
        round: 0,
        contribution_id: "r0c",
        member_id: "c",
        status: "confirmed" as const,
      },
      { ...base, contribution_id: "first", status: "failed" as const },
      { ...base, contribution_id: "retry", status: "processing" as const },
      {
        ...base,
        contribution_id: "other",
        member_id: "you",
        status: "confirmed" as const,
      },
    ],
  }
  assert.equal(myCurrentContribution(detail)?.contribution_id, "retry")
  assert.equal(
    myCurrentContribution({
      ...detail,
      contributions: [detail.contributions[3]],
    }),
    undefined
  )
  assert.equal(myCurrentContribution({ ...detail, cycle: null }), undefined)
})

test("canInvite: organiser, being set up, and a free place", async () => {
  const { canInvite } = await import("./stokvels")
  const base = {
    phase: "forming" as const,
    is_organiser: true,
    member_count: 2,
    max_members: 3,
    deactivated_at: null,
  }
  assert.equal(canInvite(base), true)
  // Deactivated: every invite would be refused with stokvel_deactivated.
  assert.equal(
    canInvite({ ...base, deactivated_at: "2026-10-19T10:00:00Z" }),
    false
  )
  assert.equal(canInvite({ ...base, member_count: 3 }), false)
  assert.equal(canInvite({ ...base, is_organiser: false }), false)
  assert.equal(canInvite({ ...base, phase: "active" }), false)
})

test("pendingInvitations keeps only unanswered ones", async () => {
  const { pendingInvitations } = await import("./stokvels")
  const invitation = {
    invitation_id: "i",
    stokvel_id: "s",
    account_reference: "a1-zar",
    invitee_name: "A",
    created_at: "",
  }
  assert.equal(
    pendingInvitations({
      invitations: [
        { ...invitation, status: "pending" },
        { ...invitation, status: "declined" },
        { ...invitation, status: "lapsed" },
      ],
    }).length,
    1
  )
})

test("moveInOrder swaps neighbours and ignores moves off the ends", async () => {
  const { moveInOrder } = await import("./stokvels")
  assert.deepEqual(moveInOrder(["a", "b", "c"], 2, -1), ["a", "c", "b"])
  assert.deepEqual(moveInOrder(["a", "b", "c"], 0, 1), ["b", "a", "c"])
  assert.deepEqual(moveInOrder(["a", "b"], 0, -1), ["a", "b"])
  assert.deepEqual(moveInOrder(["a", "b"], 1, 1), ["a", "b"])
})

test("payoutOrderWithEveryone keeps the saved order and adds newcomers", async () => {
  const { payoutOrderWithEveryone } = await import("./stokvels")
  const members = ["a", "b", "c"].map((member_id) => ({ member_id }))
  assert.deepEqual(
    payoutOrderWithEveryone({
      members: members as never,
      cycle: { status: "forming", payout_order: ["c", "gone", "a"] } as never,
    }),
    ["c", "a", "b"]
  )
  assert.deepEqual(
    payoutOrderWithEveryone({
      members: members as never,
      cycle: null,
    }),
    ["a", "b", "c"]
  )
})

test("normaliseReference trims and lower-cases", async () => {
  const { normaliseReference } = await import("./stokvels")
  assert.equal(normaliseReference(" Thandi2-ZAR "), "thandi2-zar")
})

test("startCycleBlockers lists what stops the cycle starting", async () => {
  const { startCycleBlockers } = await import("./stokvels")
  const me = { member_id: "m1", is_me: true }
  const thandi = { member_id: "m2", is_me: false }
  const beneficiary = {
    beneficiary_id: "b",
    full_name: "Tendai M.",
    payout_currency: "ZAR" as const,
  }
  assert.deepEqual(
    startCycleBlockers({
      phase: "forming",
      my_beneficiary: null,
      members: [me] as never,
      cycle: null,
    }),
    [
      "A cycle needs at least 2 members.",
      "Choose your payout beneficiary.",
      "Set the payout order.",
    ]
  )
  // Other members' choices are not on the response.
  assert.deepEqual(
    startCycleBlockers({
      phase: "forming",
      my_beneficiary: beneficiary,
      members: [me, thandi] as never,
      cycle: { status: "forming", payout_order: ["m2", "m1"] } as never,
    }),
    []
  )
  assert.deepEqual(
    startCycleBlockers({
      phase: "active",
      my_beneficiary: null,
      members: [me] as never,
      cycle: null,
    }),
    []
  )
})
