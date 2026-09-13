import { WarningIcon } from "@phosphor-icons/react"

import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"

export function RejectionBanner({
  reason,
  status,
}: {
  reason: string | null
  status?: string | null
}) {
  if (!reason) return null

  const moreInfo = status === "more_info_required"

  return (
    <Alert variant="destructive">
      <WarningIcon />
      <AlertTitle>
        {moreInfo
          ? "A reviewer needs something from you"
          : "Your last application was not approved"}
      </AlertTitle>
      <AlertDescription>
        {reason}
        {moreInfo
          ? " Update the fields below and submit again."
          : " Fields below are filled from that attempt so you only change what needs fixing. A person will review the new application."}
      </AlertDescription>
    </Alert>
  )
}
