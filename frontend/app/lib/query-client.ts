import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query"

import { ApiError } from "~/lib/api"
import { notifyForbidden } from "~/lib/forbidden-notifier"

// Set by <AuthErrorBridge /> once Clerk context exists. The QueryClient is a
// module singleton built outside React — QueryClientProvider lives in root's
// Layout, outside ClerkProvider — so it cannot call Clerk hooks itself.
let onSessionExpired: (() => void) | null = null

export function setSessionExpiredHandler(handler: (() => void) | null) {
  onSessionExpired = handler
}

function handleError(error: unknown) {
  if (!(error instanceof ApiError)) return
  if (error.status === 401) {
    onSessionExpired?.()
    return
  }
  if (error.status === 403) {
    notifyForbidden()
  }
}

export const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError: handleError }),
  mutationCache: new MutationCache({ onError: handleError }),
  defaultOptions: {
    queries: {
      // Never retry a 4xx: the answer will not change, and retrying a 401
      // doubles every request made with a dead session.
      retry: (failureCount, error) => {
        if (
          error instanceof ApiError &&
          error.status >= 400 &&
          error.status < 500
        ) {
          return false
        }
        return failureCount < 1
      },
      refetchOnWindowFocus: false,
    },
  },
})
