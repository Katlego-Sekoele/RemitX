import type { VariantProps } from "class-variance-authority"

import { TransactionStatus } from "~/client"
import type { badgeVariants } from "~/components/ui/badge"

type BadgeVariant = NonNullable<VariantProps<typeof badgeVariants>["variant"]>

/** A ledger leg's status as the customer reads it. The labels follow a
 * transfer's settlement: queued for the worker, settling on the XRPL, done. */
const STATUS: Record<
  TransactionStatus,
  { label: string; variant: BadgeVariant }
> = {
  [TransactionStatus.PENDING]: { label: "Queued", variant: "outline" },
  [TransactionStatus.PROCESSING]: {
    label: "Settling on XRPL",
    variant: "secondary",
  },
  [TransactionStatus.CONFIRMED]: { label: "Completed", variant: "default" },
  [TransactionStatus.FAILED]: { label: "Failed", variant: "destructive" },
}

export function transferStatus(status: TransactionStatus) {
  return STATUS[status] ?? { label: status, variant: "outline" as const }
}

export function transferHref(remittanceId: string) {
  return `/app/transfers/${remittanceId}`
}
