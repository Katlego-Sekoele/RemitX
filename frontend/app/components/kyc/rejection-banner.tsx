import { WarningIcon } from "@phosphor-icons/react"

import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"

export function RejectionBanner({ reason }: { reason: string | null }) {
  if (!reason) return null

  return (
    <Alert variant="destructive">
      <WarningIcon />
      <AlertTitle>Your last application was not approved</AlertTitle>
      <AlertDescription>
        {reason} Fields below are filled from that attempt so you only change
        what needs fixing. A person will review the new application.
      </AlertDescription>
    </Alert>
  )
}
