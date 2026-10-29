import { useAuth } from "@clerk/react-router"
import { Link } from "react-router"

import { OpenDashboardButton } from "~/components/open-dashboard-button"
import { Button } from "~/components/ui/button"

export type LandingAuthActionCopy = {
  signUpLabel?: string
}

function GuestLandingActions({
  signUpLabel = "Get started",
}: LandingAuthActionCopy) {
  return (
    <>
      <Button size="lg" nativeButton={false} render={<Link to="/sign-up" />}>
        {signUpLabel}
      </Button>
      <Button
        size="lg"
        variant="outline"
        nativeButton={false}
        render={<Link to="/sign-in" />}
      >
        Sign in
      </Button>
    </>
  )
}

/** Rendered only under `ClerkTree` (see `LandingAuthActions`). */
export function ClerkLandingAuthActions({
  signUpLabel = "Get started",
}: LandingAuthActionCopy) {
  const { isSignedIn } = useAuth()

  if (!isSignedIn) {
    return <GuestLandingActions signUpLabel={signUpLabel} />
  }

  return <OpenDashboardButton size="lg" />
}
