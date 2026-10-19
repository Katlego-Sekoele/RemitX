/**
 * Helpers for showing audit log entries (R4-12, #261). Stokvel admin actions
 * (doc §5, "Audit log of admin actions") are recorded on the `stokvel` and
 * `stokvel_contract` subjects; a manual finalise also records its on-chain
 * transaction hash in `after`.
 */

import type { AuditLogRead } from "~/client"

/** The audit page's "Area" filter: `GET /admin/audit?subject_type=…`. One
 * subject per request, so each view writes one `audit.log.viewed` entry. */
export const AUDIT_AREAS = [
  { value: "stokvel", label: "Stokvels" },
  { value: "stokvel_contract", label: "Stokvel contract" },
] as const

/** Stokvel admin actions, as agreed in doc §5 (R3-12, #249). */
export const STOKVEL_AUDIT_ACTIONS = [
  { value: "stokvel.contract.paused", label: "Stokvels paused" },
  { value: "stokvel.contract.unpaused", label: "Stokvels resumed" },
  {
    value: "stokvel.round.finalised_manually",
    label: "Stokvel round released by hand",
  },
] as const

/** True for the entries the stokvel view is about. */
export function isStokvelEntry(
  entry: Pick<AuditLogRead, "subject_type" | "action">
): boolean {
  return (
    entry.subject_type === "stokvel" ||
    entry.subject_type === "stokvel_contract" ||
    entry.action.startsWith("stokvel.")
  )
}

const EVM_HASH = /^0x[0-9a-fA-F]{64}$/

/**
 * The on-chain transaction hash an entry records, if any: the first value
 * under a key ending in `tx_hash` in `after`, then `before`, that looks like
 * an EVM hash. The keys aren't fixed yet (#249), so this doesn't name one.
 */
export function auditTxHash(
  entry: Pick<AuditLogRead, "after" | "before">
): string | null {
  for (const side of [entry.after, entry.before]) {
    if (!side || typeof side !== "object") continue
    for (const [key, value] of Object.entries(side)) {
      if (key.endsWith("tx_hash") && typeof value === "string") {
        if (EVM_HASH.test(value)) return value
      }
    }
  }
  return null
}
