import { useAuth } from "@clerk/react-router"
import { useMemo } from "react"

import {
  approveDeposit,
  getKycDocumentUrl,
  getMyAccess,
  getMyRoles,
  getUserAccess,
  grantRole,
  listIntegrationMessages,
  listPendingDeposits,
  listRoles,
  listAdmins,
  listApplicationDocuments,
  listToxicCombinations,
  processDeposits,
  revokeRole,
  searchUsers,
  sendIntegrationMessage,
  uploadKycDocument,
  type DepositRow,
  type DocumentAccessUrl,
  type GrantRoleResult,
  type IntegrationMessage,
  type KycDocument,
  type MePermission,
  type MyRole,
  type PendingDeposit,
  type ProcessedDeposit,
  type Role,
  type AdminMember,
  type ToxicCombination,
  type UserAccess,
  type UserRoleGrant,
  type UserSearchResult,
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
      listApplicationDocuments: (
        applicationId: string
      ): Promise<KycDocument[]> =>
        listApplicationDocuments(getToken, applicationId),
      getKycDocumentUrl: (documentId: string): Promise<DocumentAccessUrl> =>
        getKycDocumentUrl(getToken, documentId),
      uploadKycDocument: (
        applicationId: string,
        documentType: string,
        file: File
      ): Promise<KycDocument> =>
        uploadKycDocument(getToken, applicationId, documentType, file),
      listRoles: (): Promise<Role[]> => listRoles(getToken),
      listToxicCombinations: (): Promise<ToxicCombination[]> =>
        listToxicCombinations(getToken),
      listAdmins: (): Promise<AdminMember[]> => listAdmins(getToken),
      searchUsers: (email: string): Promise<UserSearchResult[]> =>
        searchUsers(getToken, email),
      getUserAccess: (userId: string): Promise<UserAccess> =>
        getUserAccess(getToken, userId),
      grantRole: (
        userId: string,
        role: string,
        reason: string,
        toxicCombinationAcknowledged: boolean
      ): Promise<GrantRoleResult> =>
        grantRole(getToken, userId, role, reason, toxicCombinationAcknowledged),
      revokeRole: (
        userId: string,
        role: string,
        reason: string
      ): Promise<UserRoleGrant> => revokeRole(getToken, userId, role, reason),
    }),
    [getToken]
  )
}
