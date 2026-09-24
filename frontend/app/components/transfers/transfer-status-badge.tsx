import { Badge } from "~/components/ui/badge"
import { statusCopy } from "~/lib/transfers"

export function TransferStatusBadge({ status }: { status: string }) {
  const copy = statusCopy(status)
  return <Badge variant={copy.badge}>{copy.label}</Badge>
}
