import { assert, test } from "vitest"

import {
  arrangeRoster,
  clampSetupStep,
  cycleRoster,
  inviteRosterKey,
  joinedMemberIds,
  sameIds,
  setupMaxStep,
} from "./stokvel-setup"

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

const invitation = (id: string, status: string, name: string) =>
  ({
    invitation_id: id,
    status,
    invitee_name: name,
  }) as never

test("cycleRoster lists members going in, then pending invitations", () => {
  const roster = cycleRoster({
    members: [
      member("org", { is_organiser: true, is_me: true, full_name: "Ada" }),
      member("thandi", { full_name: "Thandi M." }),
    ],
    invitations: [
      invitation("inv-thandi", "accepted", "Thandi M."),
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
    invitations: [invitation("inv-thandi", "accepted", "Thandi M.")],
    cycle: { status: "forming", payout_order: ["org"] } as never,
  })
  const arranged = arrangeRoster(after, ["org"], draft)
  assert.deepEqual(
    arranged.map((person) => person.key),
    ["thandi", "org"]
  )
  assert.deepEqual(joinedMemberIds(arranged), ["thandi", "org"])
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
