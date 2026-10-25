import { assert, test } from "vitest"

import {
  DEFAULT_PAY_BY_DAYS,
  DEFAULT_PAY_BY_DEMO_MINUTES,
  demoFirstPayout,
  firstPayoutIssue,
  generateSchedule,
  payByChoices,
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
    payByBefore: 2,
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
    payByBefore: 7,
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
    payByBefore: 2,
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

test("demo: payouts 5 minutes apart from Start, as in #370's example", () => {
  // Start cycle pressed at 10:00, pay-by 2 minutes before.
  const start = new Date(2026, 10, 2, 10, 0)
  const rounds = generateSchedule({
    firstPayout: demoFirstPayout(start),
    frequency: "demo",
    rounds: 3,
    payByBefore: 2,
    now: start,
  })
  const at = (minute: number) => new Date(2026, 10, 2, 10, minute).toISOString()
  assert.deepEqual(rounds, [
    { start_time: at(0), deadline: at(3), payout_time: at(5) },
    { start_time: at(5), deadline: at(8), payout_time: at(10) },
    { start_time: at(10), deadline: at(13), payout_time: at(15) },
  ])
  assert.deepEqual(scheduleIssues(rounds), [])
})

test("demo: pay-by is in minutes and never before the round opens", () => {
  const start = new Date(2026, 10, 2, 10, 0)
  const schedule = (payByBefore: number) =>
    generateSchedule({
      firstPayout: demoFirstPayout(start),
      frequency: "demo",
      rounds: 2,
      payByBefore,
      now: start,
    })
  // On the payout time.
  assert.equal(schedule(0)[1].deadline, schedule(0)[1].payout_time)
  // 3 minutes: 10:02 and 10:07, both after their round opens.
  assert.equal(
    schedule(3)[0].deadline,
    new Date(2026, 10, 2, 10, 2).toISOString()
  )
  // More minutes than the round lasts: clamped to the opening.
  const long = schedule(30)
  assert.equal(long[0].deadline, long[0].start_time)
  assert.equal(long[1].deadline, long[1].start_time)
  assert.deepEqual(scheduleIssues(long), [])
})

test("pay-by choices follow the mode, so days never go as minutes", () => {
  assert.equal(payByChoices("demo").fallback, DEFAULT_PAY_BY_DEMO_MINUTES)
  assert.deepEqual(payByChoices("demo").options, [0, 1, 2, 3])
  assert.equal(payByChoices("demo").label(2), "2 minutes before")
  assert.equal(payByChoices("demo").label(0), "On the payout time")
  assert.equal(payByChoices("weekly").fallback, DEFAULT_PAY_BY_DAYS)
  assert.equal(payByChoices("monthly").label(1), "1 day before the payout")
})

test("weekly rounds still open the morning after the previous payout", () => {
  const rounds = generateSchedule({
    firstPayout: new Date(2026, 10, 20, 14, 0),
    frequency: "weekly",
    rounds: 2,
    payByBefore: 2,
    now: new Date(2026, 9, 16),
  })
  assert.equal(rounds[1].start_time, new Date(2026, 10, 21, 7, 0).toISOString())
  assert.equal(rounds[1].deadline, new Date(2026, 10, 25, 14, 0).toISOString())
})
