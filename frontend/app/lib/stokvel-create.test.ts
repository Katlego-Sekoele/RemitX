import { assert, test } from "vitest"

import {
  contributionIssue,
  createStokvelRequest,
  firstPayoutIssue,
  generateSchedule,
  membersIssue,
  nameIssue,
  readCreateSearch,
  resolveCreateStep,
  scheduleIssues,
  writeCreateSearch,
  type CreateSearch,
} from "./stokvel-create"

const BLANK: CreateSearch = {
  name: "",
  goal: "",
  currency: null,
  amount: "",
  members: 3,
  frequency: "monthly",
  firstPayout: "",
  time: "14:00",
  step: null,
}

test("search params round-trip and drop defaults", () => {
  const params = writeCreateSearch(BLANK, {
    name: "December groceries",
    amount: "500",
    firstPayout: "2026-10-23",
    step: "amount",
  })
  assert.equal(
    params.toString(),
    "name=December+groceries&amount=500&payout=2026-10-23&step=amount"
  )
  const read = readCreateSearch(params)
  assert.equal(read.name, "December groceries")
  assert.equal(read.members, 3)
  assert.equal(read.frequency, "monthly")
  assert.equal(read.time, "14:00")
  assert.equal(read.currency, null)
})

test("non-default members, currency and frequency are kept", () => {
  const params = writeCreateSearch(BLANK, {
    members: 2,
    currency: "USD",
    frequency: "weekly",
    time: "09:30",
  })
  const read = readCreateSearch(params)
  assert.equal(read.members, 2)
  assert.equal(read.currency, "USD")
  assert.equal(read.frequency, "weekly")
  assert.equal(read.time, "09:30")
})

test("resolveCreateStep never shows a step the data cannot support", () => {
  assert.equal(
    resolveCreateStep({ ...BLANK, step: "review" }, false, true),
    "name"
  )
  assert.equal(
    resolveCreateStep({ ...BLANK, step: "review" }, true, false),
    "amount"
  )
  assert.equal(
    resolveCreateStep({ ...BLANK, step: "review" }, true, true),
    "review"
  )
  assert.equal(
    resolveCreateStep({ ...BLANK, step: "name" }, true, true),
    "name"
  )
})

test("name, amount and members validation", () => {
  assert.equal(nameIssue("  "), "Give the stokvel a name.")
  assert.equal(nameIssue("Taxi fund"), null)
  assert.match(nameIssue("x".repeat(61)) ?? "", /60 characters/)
  assert.equal(contributionIssue(""), "empty")
  assert.equal(contributionIssue("abc"), "invalid")
  assert.equal(contributionIssue("0"), "invalid")
  assert.equal(contributionIssue("5"), "too_small")
  assert.equal(contributionIssue("500"), null)
  assert.equal(membersIssue(1), "A stokvel needs at least 2 members.")
  assert.equal(membersIssue(4), "A stokvel can have at most 3 members.")
  assert.equal(membersIssue(3), null)
})

test("first payout must be a future datetime", () => {
  const now = new Date(2026, 9, 15, 12, 0)
  assert.equal(
    firstPayoutIssue("", "14:00", now),
    "Choose the first payout day."
  )
  assert.match(firstPayoutIssue("2026-10-15", "11:00", now) ?? "", /future/)
  assert.equal(firstPayoutIssue("2026-10-15", "14:00", now), null)
  assert.match(firstPayoutIssue("2026-13-40", "14:00", now) ?? "", /look right/)
})

test("generateSchedule makes one round per member with a valid order", () => {
  const now = new Date(2026, 9, 15, 12, 0)
  const first = new Date(2026, 9, 23, 14, 0)
  const rounds = generateSchedule({
    firstPayout: first,
    frequency: "monthly",
    rounds: 3,
    now,
  })
  assert.equal(rounds.length, 3)
  assert.deepEqual(
    rounds.map((r) => r.round),
    [0, 1, 2]
  )
  assert.equal(rounds[0].start_time, now.toISOString())
  assert.equal(rounds[0].payout_time, first.toISOString())
  assert.equal(rounds[0].deadline, rounds[0].payout_time)
  // Round 2 pays out a month later and opens the morning after round 1.
  assert.equal(
    rounds[1].payout_time,
    new Date(2026, 10, 23, 14, 0).toISOString()
  )
  assert.equal(rounds[1].start_time, new Date(2026, 9, 24, 7, 0).toISOString())
  assert.deepEqual(scheduleIssues(rounds), [])

  const weekly = generateSchedule({
    firstPayout: first,
    frequency: "weekly",
    rounds: 2,
    now,
  })
  assert.equal(
    weekly[1].payout_time,
    new Date(2026, 9, 30, 14, 0).toISOString()
  )
})

test("scheduleIssues mirrors the contract's _validateSchedule", () => {
  const ok = generateSchedule({
    firstPayout: new Date(2026, 9, 23, 14, 0),
    frequency: "fortnightly",
    rounds: 2,
    now: new Date(2026, 9, 15),
  })
  assert.deepEqual(scheduleIssues(ok), [])

  const backwards = [
    ok[0],
    { ...ok[1], payout_time: ok[0].payout_time, deadline: ok[0].deadline },
  ]
  backwards[1].payout_time = new Date(2026, 9, 20, 14, 0).toISOString()
  backwards[1].deadline = backwards[1].payout_time
  // It now also opens (the morning after round 1) after its own pay-by date.
  assert.deepEqual(scheduleIssues(backwards), [
    "Round 2 opens after its pay-by date.",
    "Round 2 pays out before round 1.",
  ])

  // Equal start and pay-by is fine (the contract compares strictly).
  assert.deepEqual(
    scheduleIssues([{ ...ok[0], start_time: ok[0].deadline }]),
    []
  )
  const lateOpen = [
    { ...ok[0], start_time: new Date(2026, 9, 23, 15, 0).toISOString() },
  ]
  assert.deepEqual(scheduleIssues(lateOpen), [
    "Round 1 opens after its pay-by date.",
  ])

  const latePayBy = [
    { ...ok[0], deadline: new Date(2026, 9, 24, 14, 0).toISOString() },
  ]
  assert.deepEqual(scheduleIssues(latePayBy), [
    "Round 1's pay-by date is after its payout.",
  ])

  assert.deepEqual(scheduleIssues([{ ...ok[0], start_time: "nope" }]), [
    "Round 1 has an invalid date.",
  ])
})

test("createStokvelRequest trims and defaults", () => {
  const rounds = generateSchedule({
    firstPayout: new Date(2026, 9, 23, 14, 0),
    frequency: "monthly",
    rounds: 2,
    now: new Date(2026, 9, 15),
  })
  const body = createStokvelRequest(
    { ...BLANK, name: " Taxi fund ", goal: " ", amount: "300" },
    rounds
  )
  assert.equal(body.name, "Taxi fund")
  assert.equal(body.goal, null)
  assert.equal(body.currency, "ZAR")
  assert.equal(body.contribution_fiat_amount, "300")
  assert.equal(body.rounds.length, 2)
})
