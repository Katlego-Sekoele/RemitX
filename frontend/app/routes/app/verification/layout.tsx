import { Outlet } from "react-router"

import { AppPageFrame } from "~/components/app-dashboard/app-page-frame"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { Skeleton } from "~/components/ui/skeleton"
import { useKycReferenceQuery } from "~/hooks/use-kyc-reference"
import type { Route } from "./+types/layout"

export function meta(): Route.MetaDescriptors {
  return [
    { title: "Verification — RemitX" },
    { name: "robots", content: "noindex" },
  ]
}

/** Every verification page: under Profile, and with countries and identity
 * schemes loaded, which the pages read synchronously. */
export default function VerificationLayout() {
  const reference = useKycReferenceQuery()

  return (
    <AppPageFrame
      module="routes/app/verification/history.tsx"
      parents={[{ label: "Profile", href: "/app/profile" }]}
    >
      {reference.isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : reference.error ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load verification</AlertTitle>
          <AlertDescription>
            {reference.error instanceof Error
              ? reference.error.message
              : "Please try again."}
          </AlertDescription>
        </Alert>
      ) : (
        <Outlet />
      )}
    </AppPageFrame>
  )
}
