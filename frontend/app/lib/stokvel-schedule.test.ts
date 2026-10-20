import { assert, test } from "vitest"

import {
  firstPayoutIssue,
  generateSchedule,
  scheduleIssues,
} from "./stokvel-schedule"

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

test("generateSchedule makes one round per member, in the API's shape", () => {
  const now = new Date(2026, 9, 15, 12, 0)
  const first = new Date(2026, 9, 23, 14, 0)
  const rounds = generateSchedule({
    firstPayout: first,
    frequency: "monthly",
    rounds: 3,
    now,
  })
  assert.equal(rounds.length, 3)
  // Exactly the API's fields: no round number, ISO times with an offset.
  assert.deepEqual(Object.keys(rounds[0]).sort(), [
    "deadline",
    "payout_time",
    "start_time",
  ])
  assert.match(rounds[0].payout_time, /Z$/)
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

test("generateSchedule puts the pay-by date before the payout when asked", () => {
  const rounds = generateSchedule({
    firstPayout: new Date(2026, 10, 20, 14, 0),
    frequency: "monthly",
    rounds: 2,
    payByDaysBefore: 2,
    now: new Date(2026, 9, 16),
  })
  assert.equal(rounds[0].deadline, new Date(2026, 10, 18, 14, 0).toISOString())
  assert.equal(rounds[1].deadline, new Date(2026, 11, 18, 14, 0).toISOString())
  assert.deepEqual(scheduleIssues(rounds), [])

  // Weekly with a week's notice: round 2's pay-by is the day it opens.
  const tight = generateSchedule({
    firstPayout: new Date(2026, 10, 20, 14, 0),
    frequency: "weekly",
    rounds: 2,
    payByDaysBefore: 7,
    now: new Date(2026, 9, 16),
  })
  assert.equal(tight[1].deadline, tight[1].start_time)
  assert.deepEqual(scheduleIssues(tight), [])
})

test("a first payout within the pay-by days is due when round 1 opens", () => {
  // Marc's case on #359: now 20 Oct 12:00, first payout 21 Oct 14:00.
  const now = new Date(2026, 9, 20, 12, 0)
  const rounds = generateSchedule({
    firstPayout: new Date(2026, 9, 21, 14, 0),
    frequency: "monthly",
    rounds: 2,
    payByDaysBefore: 2,
    now,
  })
  assert.equal(rounds[0].deadline, now.toISOString())
  assert.equal(rounds[1].deadline, new Date(2026, 10, 19, 14, 0).toISOString())
  assert.deepEqual(scheduleIssues(rounds), [])
})

test("scheduleIssues mirrors the contract's _validateSchedule", () => {
  const ok = generateSchedule({
    firstPayout: new Date(2026, 9, 23, 14, 0),
    frequency: "fortnightly",
    rounds: 2,
    now: new Date(2026, 9, 15),
  })
  assert.deepEqual(scheduleIssues(ok), [])

  const backwardsPayout = new Date(2026, 9, 20, 14, 0).toISOString()
  assert.deepEqual(
    scheduleIssues([
      ok[0],
      { ...ok[1], payout_time: backwardsPayout, deadline: backwardsPayout },
    ]),
    ["Round 2 opens after its pay-by date.", "Round 2 pays out before round 1."]
  )
  // Equal start and pay-by is fine (the contract compares strictly).
  assert.deepEqual(
    scheduleIssues([{ ...ok[0], start_time: ok[0].deadline }]),
    []
  )
  assert.deepEqual(
    scheduleIssues([
      { ...ok[0], start_time: new Date(2026, 9, 23, 15, 0).toISOString() },
    ]),
    ["Round 1 opens after its pay-by date."]
  )
  assert.deepEqual(
    scheduleIssues([
      { ...ok[0], deadline: new Date(2026, 9, 24, 14, 0).toISOString() },
    ]),
    ["Round 1's pay-by date is after its payout."]
  )
  assert.deepEqual(scheduleIssues([{ ...ok[0], start_time: "nope" }]), [
    "Round 1 has an invalid date.",
  ])
})
