/**
 * Staff settlement recovery: labels and guards for stuck remittance groups.
 */

import type { SettlementRecoveryKind } from "~/client"

export const STUCK_SETTLEMENTS_PATH = "/admin/stuck-settlements"

export function canRetryEnqueue(kind: SettlementRecoveryKind): boolean {
  return kind === "retry_enqueue"
}

type BadgeVariant = "default" | "secondary" | "outline" | "destructive"

export type RecoveryKindCopy = {
  label: string
  badge: BadgeVariant
  retryHint: string
}

const RECOVERY_KIND_COPY: Record<SettlementRecoveryKind, RecoveryKindCopy> = {
  retry_enqueue: {
    label: "Retry enqueue",
    badge: "secondary",
    retryHint:
      "Every leg is still pending — safe to re-publish the settlement job.",
  },
  manual_only: {
    label: "Manual only",
    badge: "destructive",
    retryHint:
      "Legs are processing or failed. Check the burn hash, worker logs, and XRPL testnet. API retry is blocked to avoid double-burn.",
  },
  none: {
    label: "None",
    badge: "outline",
    retryHint: "Not eligible for automatic recovery.",
  },
}

export function recoveryKindCopy(
  kind: SettlementRecoveryKind
): RecoveryKindCopy {
  return RECOVERY_KIND_COPY[kind] ?? RECOVERY_KIND_COPY.none
}
