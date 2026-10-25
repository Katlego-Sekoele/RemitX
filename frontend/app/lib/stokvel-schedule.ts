/**
 * The round schedule the Organiser sets before starting a cycle (R4-06,
 * #255). `POST /stokvels/{id}/cycles` (R2-10, #232) takes one round per
 * current member, in payout order, as `{ start_time, deadline, payout_time }`
 * (no round number: the position is the round). The checks mirror the
 * contract's `_validateSchedule`, so a bad schedule is caught before submit.
 */

import {
  addDays,
  addMinutes,
  addMonths,
  addWeeks,
  isValid,
  max,
  parse,
  set,
} from "date-fns"

import type { StokvelRoundTimesRequest } from "~/client"

/** One round's times, ISO 8601 with an offset (`toISOString()`): the API's
 * `StokvelRoundTimesRequest` (#348). `deadline` is the pay-by date
 * (informational, D7); the pool is never released before `payout_time`
 * (D12). */
export type StokvelRoundTimes = StokvelRoundTimesRequest

export const FREQUENCIES = [
  { key: "weekly", label: "Weekly" },
  { key: "fortnightly", label: "Every 2 weeks" },
  { key: "monthly", label: "Monthly" },
  // Rounds a few minutes apart, so a whole cycle runs during the demo (brief
  // §7.5, R4-14 #370). A round still can't release before its payout time.
  { key: "demo", label: "Every 5 minutes (demo)" },
] as const

export type Frequency = (typeof FREQUENCIES)[number]["key"]

export function isFrequency(value: unknown): value is Frequency {
  return FREQUENCIES.some((candidate) => candidate.key === value)
}

export const DEFAULT_PAYOUT_TIME = "14:00"

/** Pay-by options, in days before each payout (Q4 B: members see a pay-by
 * date and a separate payout time; the business team's vote, 16 Oct). */
export const PAY_BY_OPTIONS = [0, 1, 2, 3, 5, 7] as const
export const DEFAULT_PAY_BY_DAYS = 2

export function payByLabel(days: number): string {
  if (days === 0) return "On the payout day"
  return days === 1 ? "1 day before the payout" : `${days} days before`
}

/** Minutes between payouts, and from Start cycle to the first, in demo mode. */
export const DEMO_INTERVAL_MINUTES = 5

/** Demo pay-by options, in minutes before each payout. */
export const PAY_BY_DEMO_OPTIONS = [0, 1, 2, 3] as const
export const DEFAULT_PAY_BY_DEMO_MINUTES = 2

export function payByDemoLabel(minutes: number): string {
  if (minutes === 0) return "On the payout time"
  return minutes === 1 ? "1 minute before" : `${minutes} minutes before`
}

/** The pay-by choices for a frequency: days, or minutes in demo mode. */
export function payByChoices(frequency: Frequency): {
  options: readonly number[]
  fallback: number
  label: (value: number) => string
} {
  return frequency === "demo"
    ? {
        options: PAY_BY_DEMO_OPTIONS,
        fallback: DEFAULT_PAY_BY_DEMO_MINUTES,
        label: payByDemoLabel,
      }
    : {
        options: PAY_BY_OPTIONS,
        fallback: DEFAULT_PAY_BY_DAYS,
        label: payByLabel,
      }
}

/** The demo's first payout: a few minutes after Start cycle is pressed. */
export function demoFirstPayout(now: Date = new Date()): Date {
  return addMinutes(now, DEMO_INTERVAL_MINUTES)
}

const ISO_DATE = "yyyy-MM-dd"

/** The first payout as a local datetime, or null while unset or malformed. */
export function firstPayoutDate(
  firstPayout: string,
  time: string
): Date | null {
  if (!firstPayout) return null
  const parsed = parse(
    `${firstPayout} ${time || DEFAULT_PAYOUT_TIME}`,
    `${ISO_DATE} HH:mm`,
    new Date()
  )
  return isValid(parsed) ? parsed : null
}

export function firstPayoutIssue(
  firstPayout: string,
  time: string,
  now: Date = new Date()
): string | null {
  if (!firstPayout) return "Choose the first payout day."
  const date = firstPayoutDate(firstPayout, time)
  if (!date) return "That date and time don't look right."
  if (date <= now) return "The first payout must be in the future."
  return null
}

function stepPayout(first: Date, frequency: Frequency, round: number): Date {
  switch (frequency) {
    case "weekly":
      return addWeeks(first, round)
    case "fortnightly":
      return addWeeks(first, 2 * round)
    case "monthly":
      return addMonths(first, round)
    case "demo":
      return addMinutes(first, DEMO_INTERVAL_MINUTES * round)
  }
}

/** When a later round opens: the morning after the previous payout. */
const ROUND_OPENS_AT = { hours: 7, minutes: 0, seconds: 0, milliseconds: 0 }

/**
 * One round per member from a first payout and a cadence. Round 1 opens now.
 * Each later round opens the morning after the previous payout, or, in demo
 * mode, at the previous payout itself (the next morning would be after its
 * own payout). The pay-by is `payByBefore` days before each payout (minutes
 * in demo mode), but never before its round opens (a first payout within
 * those days, or a weekly cycle with a week's notice).
 */
export function generateSchedule({
  firstPayout,
  frequency,
  rounds,
  payByBefore = 0,
  now = new Date(),
}: {
  firstPayout: Date
  frequency: Frequency
  rounds: number
  payByBefore?: number
  now?: Date
}): StokvelRoundTimes[] {
  const demo = frequency === "demo"
  const schedule: StokvelRoundTimes[] = []
  let previousPayout: Date | null = null
  for (let round = 0; round < rounds; round++) {
    const payout = stepPayout(firstPayout, frequency, round)
    const start = !previousPayout
      ? now
      : demo
        ? previousPayout
        : set(addDays(previousPayout, 1), ROUND_OPENS_AT)
    const payBy = demo
      ? addMinutes(payout, -payByBefore)
      : addDays(payout, -payByBefore)
    schedule.push({
      start_time: start.toISOString(),
      deadline: max([start, payBy]).toISOString(),
      payout_time: payout.toISOString(),
    })
    previousPayout = payout
  }
  return schedule
}

/**
 * The contract's `_validateSchedule`: per round start ≤ pay-by ≤ payout,
 * and starts and payouts never go backwards from one round to the next.
 */
export function scheduleIssues(rounds: readonly StokvelRoundTimes[]): string[] {
  const issues: string[] = []
  rounds.forEach((current, i) => {
    const start = Date.parse(current.start_time)
    const deadline = Date.parse(current.deadline)
    const payout = Date.parse(current.payout_time)
    const label = `Round ${i + 1}`
    if ([start, deadline, payout].some(Number.isNaN)) {
      issues.push(`${label} has an invalid date.`)
      return
    }
    if (start > deadline) issues.push(`${label} opens after its pay-by date.`)
    if (deadline > payout) {
      issues.push(`${label}'s pay-by date is after its payout.`)
    }
    if (i > 0) {
      const previous = rounds[i - 1]
      if (start < Date.parse(previous.start_time)) {
        issues.push(`${label} opens before round ${i}.`)
      }
      if (payout < Date.parse(previous.payout_time)) {
        issues.push(`${label} pays out before round ${i}.`)
      }
    }
  })
  return issues
}
