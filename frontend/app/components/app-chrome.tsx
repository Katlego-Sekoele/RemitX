import type { ReactNode } from "react"
import { Link, useLocation } from "react-router"

import { AuthControls } from "~/components/auth-controls"
import { RemitXLogo } from "~/components/remitx-logo"
import { ThemeToggle } from "~/components/theme-toggle"
import { Button } from "~/components/ui/button"
import { SITE_NAME } from "~/lib/site"

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
        nativeButton={false}
        render={<Link to="/" aria-label="RemitX home" />}
      >
        <RemitXLogo className="size-6" />
      </Button>
    </div>
  )
}

/**
 * Site chrome: marketing top bar on the landing page; compact controls
 * elsewhere; theme-only on auth routes.
 */
export function AppChrome() {
  const { pathname } = useLocation()
  const onAuth =
    pathname.startsWith("/sign-in") || pathname.startsWith("/sign-up")
  const onLanding = pathname === "/"

  if (onAuth) {
    return (
      <ChromeBar>
        <ThemeToggle />
      </ChromeBar>
    )
  }

  if (onLanding) {
    return (
      <header className="sticky top-0 z-50 border-b border-border/80 bg-background/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between gap-4 px-6">
          <Link
            to="/"
            className="flex items-center gap-2.5 text-foreground"
            aria-label={`${SITE_NAME} home`}
          >
            <RemitXLogo className="size-7" />
            <span className="font-heading text-sm font-semibold tracking-tight">
              {SITE_NAME}
            </span>
          </Link>
          <div className="flex items-center gap-2">
            <AuthControls />
            <ThemeToggle />
          </div>
        </div>
      </header>
    )
  }

  return (
    <>
      <HomeLink />
      <ChromeBar>
        <AuthControls />
        <ThemeToggle />
      </ChromeBar>
    </>
  )
}
