import { Badge } from "~/components/ui/badge"
import { transferStatus } from "~/lib/transfer-status"

export function StatusBadge({ status }: { status: string }) {
  const { label, variant } = transferStatus(status)
  return <Badge variant={variant}>{label}</Badge>
}
