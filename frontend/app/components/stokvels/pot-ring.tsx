import { formatMoney } from "~/lib/money"

const RADIUS = 74
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

/**
 * The pot: a ring that fills as members pay, "2 of 3 paid" in the middle
 * (product docx §3). One hue on a muted track, so it reads in both themes.
 */
export function PotRing({
  paid,
  total,
  collected,
  pool,
  currency,
}: {
  paid: number
  total: number
  /** What is in the pot so far, in the Stokvel currency. */
  collected: string
  pool: string
  currency: string
}) {
  const fraction = total > 0 ? Math.min(paid / total, 1) : 0
  return (
    <div
      className="relative mx-auto size-44"
      role="img"
      aria-label={`${paid} of ${total} members have paid`}
    >
      <svg viewBox="0 0 176 176" className="size-full -rotate-90">
        <circle
          cx="88"
          cy="88"
          r={RADIUS}
          fill="none"
          strokeWidth="14"
          className="stroke-muted"
        />
        <circle
          cx="88"
          cy="88"
          r={RADIUS}
          fill="none"
          strokeWidth="14"
          strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={CIRCUMFERENCE * (1 - fraction)}
          className="stroke-brand-cyan transition-[stroke-dashoffset] duration-700 ease-out motion-reduce:transition-none"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-0.5">
        <span className="font-heading text-2xl font-bold tabular-nums">
          {formatMoney(collected, currency)}
        </span>
        <span className="text-xs text-muted-foreground">
          {paid} of {total} paid
        </span>
        <span className="text-xs text-muted-foreground">
          of {formatMoney(pool, currency)} pool
        </span>
      </div>
    </div>
  )
}
