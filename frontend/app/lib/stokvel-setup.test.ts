import { assert, test } from "vitest"

import {
  arrangeRoster,
  clampSetupStep,
  cycleRoster,
  inviteRosterKey,
  joinedMemberIds,
  sameIds,
  setupMaxStep,
  setupNotice,
  setupPeopleHint,
} from "./stokvel-setup"
import { invitationsAwaitingContinuation, startCycleBlockers } from "./stokvels"

const member = (id: string, extra: Record<string, unknown> = {}) =>
  ({
    member_id: id,
    user_id: `user-${id}`,
    full_name: id,
    is_organiser: false,
    is_me: false,
    in_cycle: true,
    ...extra,
  }) as never

const invitation = (
  id: string,
  status: string,
  name: string | null,
  userId: string | null = null
) =>
  ({
    invitation_id: id,
    status,
    invitee_name: name,
    invitee_user_id: userId,
  }) as never

test("cycleRoster lists members going in, then pending invitations", () => {
  const roster = cycleRoster({
    members: [
      member("org", { is_organiser: true, is_me: true, full_name: "Ada" }),
      member("thandi", { full_name: "Thandi M." }),
    ],
    invitations: [
      invitation("inv-thandi", "accepted", "Thandi M.", "user-thandi"),
      invitation("inv-sipho", "pending", "Sipho K."),
      invitation("inv-no", "declined", "No P."),
    ],
    cycle: { status: "forming", payout_order: [] } as never,
  })

  assert.deepEqual(
    roster.map((person) => [person.key, person.status, person.invitationId]),
    [
      ["org", "organiser", null],
      ["thandi", "accepted", "inv-thandi"],
      [inviteRosterKey("inv-sipho"), "pending", "inv-sipho"],
    ]
  )
  assert.equal(roster[0]?.name, "You")
})

test("arrangeRoster keeps a pending invite's place once they join", () => {
  const before = cycleRoster({
    members: [member("org", { is_organiser: true })],
    invitations: [invitation("inv-thandi", "pending", "Thandi M.")],
    cycle: { status: "forming", payout_order: ["org"] } as never,
  })
  const draft = [inviteRosterKey("inv-thandi"), "org"]
  assert.deepEqual(
    arrangeRoster(before, ["org"], draft).map((person) => person.key),
    [inviteRosterKey("inv-thandi"), "org"]
  )

  const after = cycleRoster({
    members: [
      member("org", { is_organiser: true }),
      member("thandi", { full_name: "Thandi M." }),
    ],
    invitations: [
      invitation("inv-thandi", "accepted", "Thandi M.", "user-thandi"),
    ],
    cycle: { status: "forming", payout_order: ["org"] } as never,
  })
  const arranged = arrangeRoster(after, ["org"], draft)
  assert.deepEqual(
    arranged.map((person) => person.key),
    ["thandi", "org"]
  )
  assert.deepEqual(joinedMemberIds(arranged), ["thandi", "org"])
})

test("cycleRoster matches an accepted invitation by user id", () => {
  const roster = cycleRoster({
    members: [
      member("a", { full_name: "Thandi M.", user_id: "user-a" }),
      member("b", { full_name: "Thandi M.", user_id: "user-b" }),
      member("c", { full_name: null, user_id: "user-c" }),
    ],
    invitations: [
      invitation("inv-b", "accepted", "Thandi M.", "user-b"),
      invitation("inv-a", "accepted", "Thandi M.", "user-a"),
      invitation("inv-c", "accepted", null, "user-c"),
    ],
    cycle: { status: "forming", payout_order: [] } as never,
  })

  assert.deepEqual(
    roster.map((person) => [person.key, person.invitationId]),
    [
      ["a", "inv-a"],
      ["b", "inv-b"],
      ["c", "inv-c"],
    ]
  )
})

test("arrangeRoster falls back to the saved member order", () => {
  const roster = cycleRoster({
    members: [member("a"), member("b")],
    invitations: [invitation("inv", "pending", "C")],
    cycle: { status: "forming", payout_order: ["b", "a"] } as never,
  })
  assert.deepEqual(
    arrangeRoster(roster, ["b", "a"], null).map((person) => person.key),
    ["b", "a", inviteRosterKey("inv")]
  )
})

test("setupMaxStep locks later steps", () => {
  assert.equal(
    setupMaxStep({ rosterCount: 1, scheduleReady: false, canStart: false }),
    1
  )
  assert.equal(
    setupMaxStep({ rosterCount: 3, scheduleReady: false, canStart: false }),
    3
  )
  assert.equal(
    setupMaxStep({ rosterCount: 3, scheduleReady: true, canStart: false }),
    3
  )
  assert.equal(
    setupMaxStep({ rosterCount: 3, scheduleReady: true, canStart: true }),
    4
  )
  assert.equal(clampSetupStep("start", 3), "schedule")
  assert.equal(clampSetupStep("people", 1), "people")
})

test("sameIds compares order", () => {
  assert.equal(sameIds(["a", "b"], ["a", "b"]), true)
  assert.equal(sameIds(["a", "b"], ["b", "a"]), false)
})

// The Organiser, plus `others` who have joined; invitations as given.
const forming = (
  others: string[],
  invitations: ReturnType<typeof invitation>[]
) => ({
  members: [
    member("org", { is_organiser: true, is_me: true }),
    ...others.map((id) => member(id)),
  ],
  invitations,
  cycle: { status: "forming", payout_order: [] } as never,
})

test("setupNotice counts the Organiser and everyone invited", () => {
  const detail = forming(
    [],
    [
      invitation("a", "pending", "A"),
      invitation("b", "pending", "B"),
      invitation("c", "pending", "C"),
    ]
  )
  assert.equal(setupNotice(detail)?.title, "1 of 4 joined")
  assert.equal(cycleRoster(detail).length, 4)
})

test("setupNotice counts up as people accept", () => {
  const detail = forming(
    ["a", "b"],
    [
      invitation("a", "accepted", "A", "user-a"),
      invitation("b", "accepted", "B", "user-b"),
      invitation("c", "pending", "C"),
    ]
  )
  assert.equal(setupNotice(detail)?.title, "3 of 4 joined")
})

test("a declined or revoked invitation leaves the count and the rounds", () => {
  for (const status of ["declined", "revoked", "lapsed"]) {
    const detail = forming(
      [],
      [
        invitation("a", "pending", "A"),
        invitation("b", "pending", "B"),
        invitation("c", status, "C"),
      ]
    )
    assert.equal(setupNotice(detail)?.title, "1 of 3 joined", status)
    assert.equal(cycleRoster(detail).length, 3, status)
  }
})

test("setupNotice says there are enough once everyone left has joined", () => {
  const detail = forming(
    ["a", "b"],
    [
      invitation("a", "accepted", "A", "user-a"),
      invitation("b", "accepted", "B", "user-b"),
      invitation("c", "declined", "C"),
    ]
  )
  assert.deepEqual(setupNotice(detail), {
    title: "3 of 3 joined",
    description: "You have enough members to start the cycle.",
  })
  assert.equal(cycleRoster(detail).length, 3)
})

test("setupNotice asks for an invite when the Organiser is alone", () => {
  assert.equal(setupNotice(forming([], []))?.title, "Only you so far")
  assert.equal(
    setupNotice(forming([], [invitation("a", "revoked", "A")]))?.title,
    "Only you so far"
  )
})

test("setupNotice waits on last cycle's members who haven't continued", () => {
  const detail = {
    members: [
      member("org", { is_organiser: true, is_me: true }),
      member("a"),
      member("b", { in_cycle: false }),
    ],
    invitations: [invitation("c", "pending", "C")],
    previous_cycle: {} as never,
  }
  const notice = setupNotice(detail)
  assert.equal(notice?.title, "2 of 4 joined")
  assert.include(notice?.description, "1 member hasn't said yet")
  // They aren't on the roster until they continue.
  assert.equal(cycleRoster({ ...detail, cycle: null as never }).length, 3)
})

test("after a cycle, the Organiser alone waits on those still deciding", () => {
  const detail = {
    members: [
      member("org", { is_organiser: true, is_me: true }),
      member("petrus", { full_name: "Petrus", in_cycle: false }),
      member("priya", { full_name: "Priya", in_cycle: false }),
    ],
    invitations: [
      invitation("p1", "accepted", "Petrus", "user-petrus"),
      invitation("p2", "accepted", "Priya", "user-priya"),
    ],
    cycle: null,
    previous_cycle: { cycle_number: 2 } as never,
  }
  const notice = setupNotice(detail)
  assert.equal(notice?.title, "1 of 3 joined")
  assert.include(notice?.description, "2 members haven't said yet")
  assert.equal(
    setupPeopleHint(detail, 1),
    "Waiting for Petrus and Priya to join cycle 3."
  )
  assert.equal(setupPeopleHint(detail, 2), null)
  assert.equal(
    setupPeopleHint({ ...detail, previous_cycle: null }, 1),
    "Invite at least one person."
  )
})

// Waiting on the last cycle's members must only change what setup says.
// Cycle 1, who goes into the cycle and what blocks the start stay as before.

const beneficiary = {
  beneficiary_id: "b",
  full_name: "Tendai M.",
  payout_currency: "ZAR" as const,
}

// Cycle 2 being set up: the Organiser, then the last cycle's members with
// whether each has continued.
const nextCycle = (
  others: Record<string, boolean>,
  invitations: ReturnType<typeof invitation>[] = []
) => ({
  phase: "forming" as const,
  my_beneficiary: beneficiary,
  members: [
    member("org", { is_organiser: true, is_me: true }),
    ...Object.entries(others).map(([id, in_cycle]) =>
      member(id, { full_name: id, in_cycle })
    ),
  ],
  invitations: [
    ...Object.keys(others).map((id) =>
      invitation(`inv-${id}`, "accepted", id, `user-${id}`)
    ),
    ...invitations,
  ],
  cycle: { status: "forming", payout_order: [] } as never,
  previous_cycle: { cycle_number: 1 } as never,
})

test("cycle 1 setup reads as it did before", () => {
  assert.deepEqual(
    setupNotice(forming(["a"], [invitation("b", "pending", "B")])),
    {
      title: "2 of 3 joined",
      description:
        "You can start the cycle once everyone you've invited has joined. A cycle needs at least 2 members, you included.",
    }
  )
  assert.deepEqual(setupNotice(forming([], [])), {
    title: "Only you so far",
    description:
      "Invite at least one person. A cycle needs at least 2 members, you included.",
  })
  // Members who joined in cycle 1 are never "deciding", even with
  // `in_cycle` false: that flag only matters once a cycle has closed.
  const notContinued = {
    ...forming(["a"], [invitation("a", "accepted", "A", "user-a")]),
    members: [
      member("org", { is_organiser: true, is_me: true }),
      member("a", { in_cycle: false }),
    ],
  }
  assert.equal(setupNotice(notContinued).title, "2 of 2 joined")
  assert.equal(invitationsAwaitingContinuation(notContinued).size, 0)
})

test("the people hint matches the old one outside cycle 2", () => {
  for (const count of [0, 1, 2, 5]) {
    assert.equal(
      setupPeopleHint(forming([], []), count),
      count < 2 ? "Invite at least one person." : null,
      String(count)
    )
  }
})

test("cycle 2 with everyone continued looks like a finished cycle 1", () => {
  const detail = nextCycle({ petrus: true, priya: true })
  assert.deepEqual(setupNotice(detail), {
    title: "3 of 3 joined",
    description: "You have enough members to start the cycle.",
  })
  assert.equal(setupPeopleHint(detail, cycleRoster(detail).length), null)
  assert.equal(invitationsAwaitingContinuation(detail).size, 0)
  assert.deepEqual(
    cycleRoster(detail).map((person) => [person.key, person.status]),
    [
      ["org", "organiser"],
      ["petrus", "accepted"],
      ["priya", "accepted"],
    ]
  )
})

test("members still deciding stay out of the roster and the steps", () => {
  const detail = nextCycle({ petrus: false, priya: false })
  const roster = cycleRoster(detail)
  assert.deepEqual(
    roster.map((person) => person.key),
    ["org"]
  )
  assert.deepEqual(joinedMemberIds(roster), ["org"])
  assert.equal(
    setupMaxStep({
      rosterCount: roster.length,
      scheduleReady: true,
      canStart: false,
    }),
    1
  )
  // Still not enough people to start: the deciding ones don't count.
  assert.include(
    startCycleBlockers(detail, joinedMemberIds(roster)),
    "A cycle needs at least 2 members."
  )
})

test("someone still deciding doesn't block the start", () => {
  const detail = nextCycle({ petrus: true, priya: false })
  const memberIds = joinedMemberIds(cycleRoster(detail))
  assert.deepEqual(memberIds, ["org", "petrus"])
  assert.equal(setupPeopleHint(detail, memberIds.length), null)
  assert.deepEqual(startCycleBlockers(detail, memberIds), [])
  // The notice still says they will be left out.
  const notice = setupNotice(detail)
  assert.equal(notice?.title, "2 of 3 joined")
  assert.include(notice?.description, "1 member hasn't said yet")
  assert.include(notice?.description, "left out")
})

test("a pending invitation still blocks the start alongside deciders", () => {
  const detail = nextCycle({ petrus: true, priya: false }, [
    invitation("inv-sam", "pending", "Sam"),
  ])
  const roster = cycleRoster(detail)
  assert.deepEqual(
    roster.map((person) => [person.key, person.status]),
    [
      ["org", "organiser"],
      ["petrus", "accepted"],
      [inviteRosterKey("inv-sam"), "pending"],
    ]
  )
  assert.include(
    startCycleBlockers(detail, joinedMemberIds(roster)),
    "Wait for Sam to accept their invitation."
  )
  const notice = setupNotice(detail)
  assert.equal(notice?.title, "2 of 4 joined")
  assert.equal(
    notice?.description,
    "You can start the cycle once everyone you've invited has joined. 1 member hasn't said yet whether they're joining this cycle. Anyone who hasn't by the time it starts is left out. A cycle needs at least 2 members, you included."
  )
})

test("only a decider's accepted invitation changes its label", () => {
  const detail = nextCycle({ petrus: false, thandi: true }, [
    // Petrus's earlier, unanswered or turned-down invitations keep theirs.
    invitation("old-petrus-declined", "declined", "petrus", "user-petrus"),
    invitation("old-petrus-revoked", "revoked", "petrus", "user-petrus"),
    // Someone who left is no longer a member: their invitation stays.
    invitation("inv-gone", "accepted", "Gone", "user-gone"),
  ])
  assert.deepEqual([...invitationsAwaitingContinuation(detail)], ["inv-petrus"])
})

test("the people hint names an unnamed member in lower case", () => {
  const detail = {
    members: [
      member("org", { is_organiser: true, is_me: true }),
      member("x", { full_name: null, in_cycle: false }),
    ],
    cycle: null,
    previous_cycle: { cycle_number: 2 } as never,
  }
  assert.equal(
    setupPeopleHint(detail, 1),
    "Waiting for a member to join cycle 3."
  )
})
