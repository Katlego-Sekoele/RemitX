import { format, parseISO } from "date-fns"

import { formatMoney, amountToCents } from "~/lib/money"

/** "2026-09-25" → "25 Sep", for chart axis ticks. */
export function formatChartDay(day: string): string {
  return format(parseISO(day), "d MMM")
}

/** Share of `limit` that `used` has taken, from 0 to 1. A zero limit is 0. */
export function usedShare(used: string, limit: string): number {
  const cap = amountToCents(limit)
  if (cap <= 0n) return 0
  const spent = amountToCents(used)
  if (spent <= 0n) return 0
  if (spent >= cap) return 1
  return Number(spent) / Number(cap)
}

/** The last `days` points of a series the API returned oldest-first. */
export function lastDays<T>(rows: readonly T[], days: number): T[] {
  return rows.slice(Math.max(0, rows.length - days))
}

/** A decimal string as a chart coordinate. Tooltips format the original. */
export function chartAmount(amount: string): number {
  return Number(amount)
}

/** A chart tooltip value back into the money format the rest of the app uses. */
export function formatChartMoney(value: unknown, currency: string): string {
  const numeric = typeof value === "number" ? value : Number(value)
  if (!Number.isFinite(numeric)) return ""
  return formatMoney(numeric.toFixed(2), currency)
}
