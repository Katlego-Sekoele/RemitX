/**
 * The create-stokvel wizard's state and rules (R4-03, #252), kept out of the
 * components so they can be tested on their own. Like the send flow, the
 * state lives in the URL's search params (`/app/stokvels/new?step=…`), so
 * browser back, a reload and the stepper's own triggers never lose it.
 */

import { addDays, addMonths, addWeeks, isValid, parse, set } from "date-fns"

import { amountToCents, MAX_AMOUNT_CENTS, toCents } from "~/lib/money"
import type { StokvelCreateRequest, StokvelScheduleRound } from "~/lib/stokvels"

/** Mirrors `MAX_STOKVEL_MEMBERS` in api/remitx_api/config.py (D3: 3 for the
 * prototype) and the contract's `MIN_MEMBERS`. */
export const MAX_STOKVEL_MEMBERS = 3
export const MIN_STOKVEL_MEMBERS = 2

/** Every customer has a ZAR account from signup. */
export const DEFAULT_STOKVEL_CURRENCY = "ZAR"

export const CREATE_STEPS = [
  { key: "name", title: "Name" },
  { key: "amount", title: "Amount and schedule" },
  { key: "review", title: "Review" },
] as const

export type CreateStep = (typeof CREATE_STEPS)[number]["key"]

export const FREQUENCIES = [
  { key: "weekly", label: "Weekly" },
  { key: "fortnightly", label: "Every 2 weeks" },
  { key: "monthly", label: "Monthly" },
] as const

export type Frequency = (typeof FREQUENCIES)[number]["key"]

export function isFrequency(value: unknown): value is Frequency {
  return FREQUENCIES.some((candidate) => candidate.key === value)
}

export const DEFAULT_PAYOUT_TIME = "14:00"

export type CreateSearch = {
  name: string
  goal: string
  /** Null defaults to ZAR; validated against the user's accounts where read. */
  currency: string | null
  /** As typed, in the Stokvel currency; validated separately. */
  amount: string
  /** Members in the cycle, the organiser included; one round each. */
  members: number
  frequency: Frequency
  /** First payout day, ISO `yyyy-MM-dd`, or "" while unset. */
  firstPayout: string
  /** Payout time of day, `HH:mm`. */
  time: string
  step: CreateStep | null
}

export function readCreateSearch(params: URLSearchParams): CreateSearch {
  const step = params.get("step")
  const frequency = params.get("frequency")
  const members = Number(params.get("members"))
  return {
    name: params.get("name") ?? "",
    goal: params.get("goal") ?? "",
    currency: params.get("currency") || null,
    amount: params.get("amount") ?? "",
    members:
      Number.isInteger(members) && members > 0 ? members : MAX_STOKVEL_MEMBERS,
    frequency: isFrequency(frequency) ? frequency : "monthly",
    firstPayout: params.get("payout") ?? "",
    time: params.get("time") || DEFAULT_PAYOUT_TIME,
    step:
      step === "name" || step === "amount" || step === "review" ? step : null,
  }
}

/** Empty or default values drop their key rather than leaving `?goal=`. */
export function writeCreateSearch(
  current: CreateSearch,
  patch: Partial<CreateSearch>
): URLSearchParams {
  const next = { ...current, ...patch }
  const params = new URLSearchParams()
  if (next.name) params.set("name", next.name)
  if (next.goal) params.set("goal", next.goal)
  if (next.currency && next.currency !== DEFAULT_STOKVEL_CURRENCY) {
    params.set("currency", next.currency)
  }
  if (next.amount) params.set("amount", next.amount)
  if (next.members !== MAX_STOKVEL_MEMBERS) {
    params.set("members", String(next.members))
  }
  if (next.frequency !== "monthly") params.set("frequency", next.frequency)
  if (next.firstPayout) params.set("payout", next.firstPayout)
  if (next.time && next.time !== DEFAULT_PAYOUT_TIME) {
    params.set("time", next.time)
  }
  if (next.step) params.set("step", next.step)
  return params
}

/** The step the page can show: no later step than the data allows. */
export function resolveCreateStep(
  search: CreateSearch,
  nameValid: boolean,
  amountValid: boolean
): CreateStep {
  if (!nameValid) return "name"
  if (search.step === "name") return "name"
  if (search.step === "review" && amountValid) return "review"
  return "amount"
}

export function createStepNumber(step: CreateStep): number {
  return CREATE_STEPS.findIndex((candidate) => candidate.key === step) + 1
}

export const MAX_NAME_LENGTH = 60

export function nameIssue(name: string): string | null {
  const trimmed = name.trim()
  if (!trimmed) return "Give the stokvel a name."
  if (trimmed.length > MAX_NAME_LENGTH) {
    return `Keep the name to ${MAX_NAME_LENGTH} characters.`
  }
  return null
}

/** The smallest contribution worth a transfer fee; the API has the final say. */
export const MIN_CONTRIBUTION = "10.00"

export type AmountIssue = "empty" | "invalid" | "too_small" | "too_large"

export function contributionIssue(amount: string): AmountIssue | null {
  if (!amount.trim()) return "empty"
  const cents = toCents(amount)
  if (cents === null || cents <= 0n) return "invalid"
  if (cents < amountToCents(MIN_CONTRIBUTION)) return "too_small"
  if (cents > MAX_AMOUNT_CENTS) return "too_large"
  return null
}

export function contributionIssueMessage(
  issue: AmountIssue,
  currencyLabel: string
): string {
  switch (issue) {
    case "empty":
      return "Enter the amount each member pays per round."
    case "invalid":
      return "Enter an amount like 500 or 500.00."
    case "too_small":
      return `The minimum is ${currencyLabel} ${MIN_CONTRIBUTION} per member.`
    case "too_large":
      return "That amount is too large."
  }
}

export function membersIssue(members: number): string | null {
  if (!Number.isInteger(members) || members < MIN_STOKVEL_MEMBERS) {
    return `A stokvel needs at least ${MIN_STOKVEL_MEMBERS} members.`
  }
  if (members > MAX_STOKVEL_MEMBERS) {
    return `A stokvel can have at most ${MAX_STOKVEL_MEMBERS} members.`
  }
  return null
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
  }
}

/** When a later round opens: the morning after the previous payout. */
const ROUND_OPENS_AT = { hours: 7, minutes: 0, seconds: 0, milliseconds: 0 }

/**
 * One round per member from a first payout day and a cadence. Round 1 opens
 * now; each later round opens the morning after the previous payout. The
 * pay-by date is the payout day (P6: one date shown to members).
 */
export function generateSchedule({
  firstPayout,
  frequency,
  rounds,
  now = new Date(),
}: {
  firstPayout: Date
  frequency: Frequency
  rounds: number
  now?: Date
}): StokvelScheduleRound[] {
  const schedule: StokvelScheduleRound[] = []
  let previousPayout: Date | null = null
  for (let round = 0; round < rounds; round++) {
    const payout = stepPayout(firstPayout, frequency, round)
    const start = previousPayout
      ? set(addDays(previousPayout, 1), ROUND_OPENS_AT)
      : now
    schedule.push({
      round,
      start_time: start.toISOString(),
      deadline: payout.toISOString(),
      payout_time: payout.toISOString(),
    })
    previousPayout = payout
  }
  return schedule
}

/**
 * The contract's `_validateSchedule`, so a bad schedule is caught before
 * submit instead of reverting with `InvalidSchedule`: per round start ≤
 * pay-by ≤ payout, and starts and payouts never go backwards.
 */
export function scheduleIssues(
  rounds: readonly StokvelScheduleRound[]
): string[] {
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

export function createStokvelRequest(
  search: CreateSearch,
  rounds: readonly StokvelScheduleRound[]
): StokvelCreateRequest {
  return {
    name: search.name.trim(),
    goal: search.goal.trim() || null,
    currency: search.currency ?? DEFAULT_STOKVEL_CURRENCY,
    contribution_fiat_amount: search.amount,
    rounds: [...rounds],
  }
}
