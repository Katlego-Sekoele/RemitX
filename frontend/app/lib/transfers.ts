/**
 * Transfer URLs, statuses and display rules. Every link to a transfer is
 * built here.
 */

export const TRANSFERS_PATH = "/app/transfers"

/** A transfer's own page. */
export function transferPath(remittanceId: string): string {
  return `${TRANSFERS_PATH}/${remittanceId}`
}

const DEFAULT_POLL_INTERVAL_MS = 3000

/** How often the status page asks again while a transfer is in flight. */
export const POLL_INTERVAL_MS = readPollInterval()

function readPollInterval(): number {
  const raw = import.meta.env.VITE_TRANSFER_POLL_INTERVAL_MS
  if (typeof raw !== "string" || raw.trim() === "")
    return DEFAULT_POLL_INTERVAL_MS
  const parsed = Number(raw)
  return Number.isFinite(parsed) && parsed > 0
    ? parsed
    : DEFAULT_POLL_INTERVAL_MS
}

/** Queued longer than this, the page says the worker may be waking up. */
export const SLOW_QUEUE_MS = 60_000

type BadgeVariant = "default" | "secondary" | "outline" | "destructive"

type StatusCopy = { label: string; badge: BadgeVariant }

/** The settlement leg's status, as the UI names it. */
const STATUS_COPY: Record<string, StatusCopy> = {
  pending: { label: "Queued", badge: "secondary" },
  processing: { label: "Settling on XRPL", badge: "outline" },
  confirmed: { label: "Completed", badge: "default" },
  failed: { label: "Failed", badge: "destructive" },
}

export function statusCopy(status: string): StatusCopy {
  return STATUS_COPY[status] ?? { label: status, badge: "outline" }
}

/** Still moving: poll until this is false. */
export function isInFlight(status: string): boolean {
  return status === "pending" || status === "processing"
}

/** Queued for longer than a warm worker would take. */
export function isSlowToStart(
  status: string,
  createdAt: string,
  now: number
): boolean {
  return status === "pending" && now - Date.parse(createdAt) > SLOW_QUEUE_MS
}

/** `A1B2…9F0E`. */
export function shortHash(hash: string): string {
  return hash.length <= 10 ? hash : `${hash.slice(0, 4)}…${hash.slice(-4)}`
}

export function explorerUrl(hash: string): string {
  return `https://testnet.xrpl.org/transactions/${hash}`
}

/** What a list row shows as the amount, and in which currency: what the
 * caller sent, or what they received. */
export function headlineAmount(transfer: {
  direction: string
  sender_amount: string | null
  sender_currency: string
  receiver_payout_estimate: string
  receiver_currency: string
}): { amount: string; currency: string } {
  return transfer.direction === "sent" && transfer.sender_amount !== null
    ? { amount: transfer.sender_amount, currency: transfer.sender_currency }
    : {
        amount: transfer.receiver_payout_estimate,
        currency: transfer.receiver_currency,
      }
}

const WHEN_FORMAT = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
})

/** A timestamp in the viewer's locale and time zone. */
export function formatWhen(value: string): string {
  return WHEN_FORMAT.format(new Date(value))
}
