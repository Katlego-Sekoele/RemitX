import type { TransferRead } from "~/client"
import { Badge } from "~/components/ui/badge"
import { statusCopy } from "~/lib/transfers"

export function TransferStatusBadge({
  status,
}: {
  status: TransferRead["status"]
}) {
  const copy = statusCopy(status)
  return <Badge variant={copy.badge}>{copy.label}</Badge>
}
