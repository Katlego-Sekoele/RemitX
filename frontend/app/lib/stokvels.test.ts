import { assert, test } from "vitest"

import {
  explorerTxUrl,
  feeShare,
  fiatToToken,
  poolAmount,
  roundLabel,
  STOKVEL_INFLIGHT_POLL_INTERVAL_MS,
  STOKVEL_POLL_INTERVAL_MS,
  stokvelDetailPollInterval,
  stokvelPath,
  stokvelPollInterval,
  tokenToFiat,
} from "./stokvels"

test("stokvel screens poll while a read is on screen", () => {
  assert.equal(stokvelPollInterval({ state: { data: undefined } }), false)
  assert.equal(
    stokvelPollInterval({ state: { data: { stokvels: [] } } }),
    STOKVEL_POLL_INTERVAL_MS
  )
  const quiet = {
    state: {
      data: {
        my_member_id: "me",
        contributions: [
          { member_id: "me", status: "confirmed" as const },
          { member_id: "you", status: "pending" as const },
        ],
      },
    },
  }
  assert.equal(stokvelDetailPollInterval(quiet), STOKVEL_POLL_INTERVAL_MS)
  assert.equal(
    stokvelDetailPollInterval({
      state: {
        data: {
          my_member_id: "me",
          contributions: [{ member_id: "me", status: "processing" as const }],
        },
      },
    }),
    STOKVEL_INFLIGHT_POLL_INTERVAL_MS
  )
  assert.equal(
    stokvelDetailPollInterval({
      state: {
        data: {
          my_member_id: "me",
          contributions: [{ member_id: "me", status: "pending" as const }],
        },
      },
    }),
    STOKVEL_INFLIGHT_POLL_INTERVAL_MS
  )
  assert.equal(stokvelDetailPollInterval({ state: { data: undefined } }), false)
  assert.equal(
    stokvelDetailPollInterval({
      state: {
        data: {
          my_member_id: "me",
          contributions: [],
          cycle: { status: "active", registered_at: null },
        },
      },
    }),
    STOKVEL_INFLIGHT_POLL_INTERVAL_MS
  )
})

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
    cycle: { cycle_id: "c", current_round: 0 },
    open_round: 1,
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
    open_round: 1,
    cycle: { cycle_id: "cyc", current_round: 0 } as never,
    contributions: [
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
      contributions: [detail.contributions[0]],
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
  assert.deepEqual(
    startCycleBlockers(
      {
        phase: "forming",
        my_beneficiary: beneficiary,
        members: [me, thandi] as never,
        cycle: { status: "forming", payout_order: ["m2", "m1"] } as never,
        invitations: [
          { status: "pending", invitee_name: "Sipho K." },
          { status: "accepted", invitee_name: "Thandi M." },
        ] as never,
      },
      ["m2", "m1"]
    ),
    ["Wait for Sipho K. to accept their invitation."]
  )
})

test("invitableBeneficiaries offers the Stokvel currency, not members", async () => {
  const { invitableBeneficiaries } = await import("./stokvels")
  const beneficiary = (id: string, currencies: string[]) =>
    ({
      beneficiary_id: id,
      linked_user_id: `user-${id}`,
      payout_currencies: currencies,
    }) as never
  const { invitable, otherCurrency } = invitableBeneficiaries(
    [
      beneficiary("zar", ["ZAR"]),
      beneficiary("usd-only", ["USD"]),
      beneficiary("both", ["ZAR", "USD"]),
      beneficiary("member", ["ZAR"]),
    ],
    {
      currency: "ZAR",
      members: [{ user_id: "user-member" }] as never,
    }
  )
  assert.deepEqual(
    invitable.map((b) => b.beneficiary_id),
    ["zar", "both"]
  )
  // The member isn't counted as left out for the currency.
  assert.equal(otherCurrency, 1)
})

test("from cycle 2, only members going in count for the order and start", async () => {
  const {
    continuationStatus,
    goingIntoCycle,
    payoutOrderWithEveryone,
    startCycleBlockers,
    undecidedMembers,
  } = await import("./stokvels")
  const member = (id: string, in_cycle: boolean, extra = {}) =>
    ({ member_id: id, in_cycle, is_me: false, ...extra }) as never
  const cycle2 = {
    phase: "forming" as const,
    is_organiser: false,
    members: [
      member("organiser", true, { is_organiser: true }),
      member("thandi", true),
      member("me", false, { is_me: true }),
    ],
    cycle: { status: "forming", payout_order: [] } as never,
    previous_cycle: { cycle_number: 1 } as never,
    my_beneficiary: null,
  }

  assert.deepEqual(
    goingIntoCycle(cycle2).map((m) => m.member_id),
    ["organiser", "thandi"]
  )
  assert.deepEqual(
    undecidedMembers(cycle2).map((m) => m.member_id),
    ["me"]
  )
  assert.deepEqual(payoutOrderWithEveryone(cycle2), ["organiser", "thandi"])
  // Two going in and a full order: only the caller's own beneficiary is
  // listed, and the undecided member doesn't block the start.
  assert.deepEqual(startCycleBlockers(cycle2, ["thandi", "organiser"]), [
    "Choose your payout beneficiary.",
  ])

  assert.equal(continuationStatus(cycle2), "undecided")
  const continued = {
    ...cycle2,
    members: [member("organiser", true), member("me", true, { is_me: true })],
  }
  assert.equal(continuationStatus(continued), "continued")
  assert.equal(
    continuationStatus({ ...cycle2, is_organiser: true }),
    "organiser"
  )
  // Cycle 1, or once the next cycle has started: nothing to choose.
  assert.equal(continuationStatus({ ...cycle2, previous_cycle: null }), "none")
  assert.equal(continuationStatus({ ...cycle2, phase: "active" }), "none")
  assert.deepEqual(
    goingIntoCycle({ ...cycle2, previous_cycle: null }).length,
    3
  )
})

test("invitationsByStatus lists pending ones first, then the rest in order", async () => {
  const { invitationsByStatus } = await import("./stokvels")
  const invitation = (id: string, status: string) =>
    ({ invitation_id: id, status }) as never
  // The API sends them newest first.
  const ordered = invitationsByStatus({
    invitations: [
      invitation("declined-new", "declined"),
      invitation("pending-new", "pending"),
      invitation("accepted", "accepted"),
      invitation("pending-old", "pending"),
      invitation("lapsed", "lapsed"),
    ],
  })
  assert.deepEqual(
    ordered.map((i: { invitation_id: string }) => i.invitation_id),
    ["pending-new", "pending-old", "declined-new", "accepted", "lapsed"]
  )
  assert.deepEqual(invitationsByStatus({ invitations: [] }), [])
})

test("accepted invitations of undecided members await the next cycle", async () => {
  const { invitationsAwaitingContinuation } = await import("./stokvels")
  const member = (id: string, in_cycle: boolean) =>
    ({ member_id: id, user_id: `user-${id}`, in_cycle }) as never
  const invitation = (id: string, status: string, userId: string) =>
    ({
      invitation_id: id,
      status,
      invitee_user_id: userId,
    }) as never
  const detail = {
    members: [
      member("org", true),
      member("petrus", false),
      member("thandi", true),
    ],
    invitations: [
      invitation("i-petrus", "accepted", "user-petrus"),
      invitation("i-thandi", "accepted", "user-thandi"),
      invitation("i-sam", "pending", "user-sam"),
    ],
    previous_cycle: { cycle_number: 1 } as never,
  }
  assert.deepEqual([...invitationsAwaitingContinuation(detail)], ["i-petrus"])
  // Cycle 1: everyone who accepted is in.
  assert.equal(
    invitationsAwaitingContinuation({ ...detail, previous_cycle: null }).size,
    0
  )
})

test("formingCycleNumber is the cycle being set up", async () => {
  const { formingCycleNumber } = await import("./stokvels")
  // The forming cycle's own number wins.
  assert.equal(
    formingCycleNumber({
      cycle: { cycle_number: 3 } as never,
      previous_cycle: { cycle_number: 2 } as never,
    }),
    3
  )
  // Else the one after the closed cycle, or 1 for a new stokvel.
  assert.equal(
    formingCycleNumber({
      cycle: null,
      previous_cycle: { cycle_number: 2 } as never,
    }),
    3
  )
  assert.equal(formingCycleNumber({ cycle: null, previous_cycle: null }), 1)
})
