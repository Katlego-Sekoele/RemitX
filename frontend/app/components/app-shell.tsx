import type { ReactNode } from "react"
import { lazy, Suspense, useEffect, useState } from "react"
import { Outlet, useLocation } from "react-router"

import { AppChrome } from "~/components/app-chrome"

const ClerkTree = lazy(() =>
  import("~/components/clerk-tree").then((module) => ({
    default: module.ClerkTree,
  }))
)

function isMarketingPath(pathname: string): boolean {
  return pathname === "/"
}

type IdleScheduler = {
  requestIdleCallback: (
    callback: IdleRequestCallback,
    options?: IdleRequestOptions
  ) => number
  cancelIdleCallback: (handle: number) => void
}

function isIdleScheduler(
  runtime: typeof globalThis
): runtime is typeof globalThis & IdleScheduler {
  return (
    "requestIdleCallback" in runtime &&
    typeof runtime.requestIdleCallback === "function" &&
    "cancelIdleCallback" in runtime &&
    typeof runtime.cancelIdleCallback === "function"
  )
}

function requestIdle(callback: () => void): () => void {
  if (isIdleScheduler(globalThis)) {
    const idleHandle = globalThis.requestIdleCallback(() => {
      callback()
    })
    return () => {
      globalThis.cancelIdleCallback(idleHandle)
    }
  }
  const timeoutHandle = globalThis.setTimeout(callback, 1)
  return () => {
    globalThis.clearTimeout(timeoutHandle)
  }
}

/**
 * Loads Clerk only off the marketing page so `/` is not blocked by clerk-js.
 * Auth and protected routes mount Clerk on the same render. Once mounted,
 * Clerk stays up (including return visits to `/`) so signed-in chrome works.
 * After idle on marketing, Clerk warms so returning sessions get UserButton.
 */
export function AppShell({ children }: { children?: ReactNode }) {
  const { pathname } = useLocation()
  const needsClerk = !isMarketingPath(pathname)
  const [keepClerk, setKeepClerk] = useState(needsClerk)

  useEffect(() => {
    if (needsClerk) {
      setKeepClerk(true)
      return
    }
    return requestIdle(() => setKeepClerk(true))
  }, [needsClerk])

  const mountClerk = needsClerk || keepClerk

  const body = (
    <>
      <AppChrome />
      {children ?? <Outlet />}
    </>
  )

  if (!mountClerk) {
    return body
  }

  // Auth routes must not render Clerk consumers outside the provider.
  // Marketing can keep showing the page while the chunk warms.
  const fallback = needsClerk ? (
    <>
      <AppChrome />
      <div
        className="flex min-h-[50vh] items-center justify-center"
        role="status"
      >
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    </>
  ) : (
    body
  )

  return (
    <Suspense fallback={fallback}>
      <ClerkTree>{body}</ClerkTree>
    </Suspense>
  )
}
