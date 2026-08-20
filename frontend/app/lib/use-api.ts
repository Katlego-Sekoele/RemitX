import { useAuth } from "@clerk/react-router"
import { useMemo } from "react"

import {
  listIntegrationMessages,
  sendIntegrationMessage,
  type IntegrationMessage,
} from "~/lib/api"

/**
 * Binds the API functions to the current Clerk session.
 *
 * Memoised on getToken so the returned object is referentially stable —
 * an unstable identity here would retrigger every TanStack Query that
 * uses one of these as its queryFn.
 */
export function useApi() {
  const { getToken } = useAuth()

  return useMemo(
    () => ({
      listIntegrationMessages: (): Promise<IntegrationMessage[]> =>
        listIntegrationMessages(getToken),
      sendIntegrationMessage: (body: string): Promise<IntegrationMessage> =>
        sendIntegrationMessage(getToken, body),
    }),
    [getToken]
  )
}
