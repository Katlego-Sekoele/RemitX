import { lazy, Suspense } from "react"
import { Link } from "react-router"

import { useClerkMounted } from "~/components/clerk-mounted"
import { Button } from "~/components/ui/button"

const ClerkAuthControls = lazy(() =>
  import("~/components/clerk-auth-controls").then((module) => ({
    default: module.ClerkAuthControls,
  }))
)

function GuestAuthLinks() {
  return (
    <>
      <Button
        size="sm"
        variant="outline"
        nativeButton={false}
        render={<Link to="/sign-up" />}
      >
        Start sending
      </Button>
      <Button size="sm" nativeButton={false} render={<Link to="/sign-in" />}>
        Sign in
      </Button>
    </>
  )
}

/** Auth CTAs for chrome — Clerk widgets only when `ClerkProvider` is up. */
export function AuthControls() {
  const clerkMounted = useClerkMounted()

  if (!clerkMounted) {
    return <GuestAuthLinks />
  }

  return (
    <Suspense fallback={<GuestAuthLinks />}>
      <ClerkAuthControls />
    </Suspense>
  )
}
