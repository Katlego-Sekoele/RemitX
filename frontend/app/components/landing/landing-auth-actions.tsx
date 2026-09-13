import { lazy, Suspense } from "react"
import { Link } from "react-router"

import { useClerkMounted } from "~/components/clerk-mounted"
import { Button } from "~/components/ui/button"

const ClerkLandingAuthActions = lazy(() =>
  import("~/components/landing/clerk-landing-auth-actions").then((module) => ({
    default: module.ClerkLandingAuthActions,
  }))
)

export type LandingAuthActionCopy = {
  signUpLabel?: string
}

function GuestLandingActions({
  signUpLabel = "Start sending",
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

/** Hero/footer CTAs — Clerk widgets only when `ClerkProvider` is up. */
export function LandingAuthActions({
  signUpLabel = "Start sending",
}: LandingAuthActionCopy) {
  const clerkMounted = useClerkMounted()

  if (!clerkMounted) {
    return <GuestLandingActions signUpLabel={signUpLabel} />
  }

  return (
    <Suspense fallback={<GuestLandingActions signUpLabel={signUpLabel} />}>
      <ClerkLandingAuthActions signUpLabel={signUpLabel} />
    </Suspense>
  )
}
