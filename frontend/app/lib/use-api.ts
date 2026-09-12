import { useAuth } from "@clerk/react-router"
import { useMemo } from "react"

import {
  approveDeposit,
  getMyAccess,
  getMyRoles,
  listIntegrationMessages,
  listPendingDeposits,
  processDeposits,
  sendIntegrationMessage,
  type DepositRow,
  type IntegrationMessage,
  type MePermission,
  type MyRole,
  type PendingDeposit,
  type ProcessedDeposit,
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
      getMyAccess: (): Promise<MePermission> => getMyAccess(getToken),
      getMyRoles: (): Promise<MyRole[]> => getMyRoles(getToken),
      processDeposits: (rows: DepositRow[]): Promise<ProcessedDeposit[]> =>
        processDeposits(getToken, rows),
      listPendingDeposits: (): Promise<PendingDeposit[]> =>
        listPendingDeposits(getToken),
      approveDeposit: (
        depositId: string,
        userId: string
      ): Promise<ProcessedDeposit> =>
        approveDeposit(getToken, depositId, userId),
    }),
    [getToken]
  )
}
