import { Show, UserButton } from "@clerk/react-router"
import { Link } from "react-router"

import { Button } from "~/components/ui/button"

/** Clerk-backed chrome controls — requires `ClerkProvider`. */
export function ClerkAuthControls() {
  return (
    <Show
      when="signed-in"
      fallback={
        <>
          <Button
            size="sm"
            variant="outline"
            nativeButton={false}
            render={<Link to="/sign-up" />}
          >
            Start sending
          </Button>
          <Button
            size="sm"
            nativeButton={false}
            render={<Link to="/sign-in" />}
          >
            Sign in
          </Button>
        </>
      }
    >
      <UserButton />
    </Show>
  )
}
