import type { badgeVariants } from "~/components/ui/badge"
import type { VariantProps } from "class-variance-authority"

type BadgeVariant = NonNullable<VariantProps<typeof badgeVariants>["variant"]>

/** A ledger leg's status as the customer reads it. The labels follow a
 * transfer's settlement: queued for the worker, settling on the XRPL, done. */
const STATUS: Record<string, { label: string; variant: BadgeVariant }> = {
  pending: { label: "Queued", variant: "outline" },
  processing: { label: "Settling on XRPL", variant: "secondary" },
  confirmed: { label: "Completed", variant: "default" },
  failed: { label: "Failed", variant: "destructive" },
}

export function transferStatus(status: string) {
  return STATUS[status] ?? { label: status, variant: "outline" as const }
}

export function transferHref(remittanceId: string) {
  return `/app/transfers/${remittanceId}`
}
