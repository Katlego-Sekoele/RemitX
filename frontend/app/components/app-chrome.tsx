import { Show, SignInButton, UserButton } from "@clerk/react-router"
import type { ReactNode } from "react"
import { Link } from "react-router"

import { ThemeToggle } from "~/components/theme-toggle"
import { Button } from "~/components/ui/button"

/**
 * The fixed top-right control cluster.
 *
 * Exported on its own so the error boundary — which renders outside
 * ClerkProvider and so cannot show auth state — can still park a theme
 * toggle in the same spot.
 */
export function ChromeBar({ children }: { children: ReactNode }) {
  return (
    <div className="fixed top-4 right-4 z-50 flex items-center gap-2">
      {children}
    </div>
  )
}

/**
 * Logo shortcut back to the landing page.
 *
 * Base UI's `render` prop swaps the underlying <button> for a router <Link>,
 * so the mark keeps the Button's focus ring and hover state while still being
 * a real anchor. The alt is empty because the link's aria-label already names
 * it — otherwise screen readers announce the destination twice.
 */
export function HomeLink() {
  return (
    <div className="fixed top-4 left-4 z-50">
      <Button
        variant="ghost"
        size="icon-lg"
        render={<Link to="/" aria-label="RemitX home" />}
      >
        <img src="/remitx-logo.svg" alt="" className="size-6" />
      </Button>
    </div>
  )
}

/**
 * Auth control plus theme toggle, on every page.
 *
 * <Show> renders null until Clerk settles, so a signed-in user reloading the
 * page never sees "Sign in" flash before their avatar. SignInButton clones the
 * Button and drives the navigation itself, which keeps the destination tied to
 * ClerkProvider's signInUrl instead of a second hardcoded "/sign-in".
 */
export function AppChrome() {
  return (
    <>
      <HomeLink />
      <ChromeBar>
        <Show
          when="signed-in"
          fallback={
            <SignInButton>
              <Button size="sm">Sign in</Button>
            </SignInButton>
          }
        >
          <UserButton />
        </Show>
        <ThemeToggle />
      </ChromeBar>
    </>
  )
}
