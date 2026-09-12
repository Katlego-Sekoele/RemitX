import { useAuth, useClerk } from "@clerk/react-router"
import { useEffect } from "react"

import { setSessionExpiredHandler } from "~/lib/query-client"

/**
 * Bridges API auth failures into UI actions the query cache cannot reach.
 *
 * 401 → Clerk sign-in (session expired or missing). 403 → ``notifyForbidden``
 * via the query cache, which admin layout turns into the access-denied page.
 * Hiding nav links is usability; server 403 is the security boundary.
 *
 * Renders nothing. Exists because the query cache is a module singleton built
 * outside React.
 */
export function AuthErrorBridge() {
  const { isSignedIn } = useAuth()
  const clerk = useClerk()

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
