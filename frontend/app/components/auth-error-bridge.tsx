import { useAuth, useClerk } from "@clerk/react-router"
import { useEffect } from "react"

import { setSessionExpiredHandler } from "~/lib/query-client"

/**
 * Sends API 401s to Clerk's sign-in redirect.
 *
 * Renders nothing. Exists because the query cache is created outside React
 * and cannot reach Clerk's context on its own.
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
