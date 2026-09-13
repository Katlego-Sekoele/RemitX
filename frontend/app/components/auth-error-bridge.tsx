import { useAuth, useClerk } from "@clerk/react-router"
import { useEffect, useLayoutEffect } from "react"

import { setTokenGetter } from "~/lib/api-client-config"
import { setSessionExpiredHandler } from "~/lib/query-client"

/**
 * Bridges Clerk into the API client and query cache, both module singletons
 * that cannot call hooks.
 *
 * The session token is handed to the generated client, which attaches it to
 * every call the spec marks as authenticated.
 *
 * Auth failures become UI actions:
 *
 * 401 → Clerk sign-in (session expired or missing). 403 → ``notifyForbidden``
 * via the query cache, which admin layout turns into the access-denied page.
 * Hiding nav links is usability; server 403 is the security boundary.
 *
 * Renders nothing.
 */
export function AuthErrorBridge() {
  const { getToken, isSignedIn } = useAuth()
  const clerk = useClerk()

  // Layout effect: runs before any passive effect in the tree, so before the
  // first query subscribes and fetches.
  useLayoutEffect(() => {
    setTokenGetter(getToken)
    return () => setTokenGetter(null)
  }, [getToken])

  useEffect(() => {
    setSessionExpiredHandler(() => {
      // Already signed out: a 401 here is expected and redirecting would
      // loop against the sign-in page's own requests.
      if (!isSignedIn) return
      clerk.redirectToSignIn()
    })
    return () => setSessionExpiredHandler(null)
  }, [clerk, isSignedIn])

  return null
}
