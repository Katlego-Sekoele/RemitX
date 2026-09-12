// `||`, not `??`: an unset GitHub secret expands to "" in the deploy
// workflow, and Vite inlines that empty string. `??` would keep it, making
// every request same-origin-relative and 404 against Static Web Apps.
const API_URL = import.meta.env.VITE_API_URL || "http://localhost:4200"

/** Mirrors BODY_MAX_LENGTH on the API. */
export const MESSAGE_MAX_LENGTH = 280

export type MessageStatus = "PENDING" | "PROCESSED"

export type IntegrationMessage = {
  id: string
  body: string
  status: MessageStatus
  created_at: string
  processed_at: string | null
}

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

/**
 * FastAPI reports validation failures as `{detail: [{msg, loc}, ...]}` and
 * everything else as `{detail: "..."}`. Flatten both into one string.
 */
async function describeFailure(response: Response): Promise<string> {
  try {
    const payload = await response.json()
    const detail = payload?.detail

    if (typeof detail === "string") return detail

    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => item?.msg)
        .filter((msg): msg is string => Boolean(msg))
      if (messages.length > 0) return messages.join("; ")
    }
  } catch {
    // Non-JSON body — fall through to the status text.
  }

  return response.statusText || `Request failed with status ${response.status}`
}

export type GetToken = () => Promise<string | null>

async function request<T>(
  getToken: GetToken,
  path: string,
  init?: RequestInit
): Promise<T> {
  const token = await getToken()

  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        // Only when there is a body to describe. `application/json` is not a
        // CORS-safelisted content type, so sending it on a bodyless GET forces
        // an OPTIONS preflight — two round trips per poll, once a second.
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        // Authorization is never CORS-safelisted, so this preflights
        // regardless. The response is cacheable, so it costs one extra round
        // trip per origin per max-age, not one per request.
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init?.headers,
      },
    })
  } catch {
    // fetch only rejects on network-level failure, which for this app almost
    // always means the API is not running or CORS blocked the call.
    throw new ApiError(`Could not reach the API at ${API_URL}`, 0)
  }

  if (!response.ok) {
    throw new ApiError(await describeFailure(response), response.status)
  }

  return (await response.json()) as T
}

export function listIntegrationMessages(
  getToken: GetToken
): Promise<IntegrationMessage[]> {
  return request<IntegrationMessage[]>(getToken, "/integration-messages")
}

export function sendIntegrationMessage(
  getToken: GetToken,
  body: string
): Promise<IntegrationMessage> {
  return request<IntegrationMessage>(getToken, "/integration-messages", {
    method: "POST",
    body: JSON.stringify({ body }),
  })
}

export type MePermission = {
  permissions: string[]
  is_admin: boolean
}

export function getMyAccess(getToken: GetToken): Promise<MePermission> {
  return request<MePermission>(getToken, "/me/permissions")
}

export type MyPermission = {
  permission: string
  description: string
}

export type MyRole = {
  name: string
  display_name: string
  description: string
  permissions: MyPermission[]
}

export function getMyRoles(getToken: GetToken): Promise<MyRole[]> {
  return request<MyRole[]>(getToken, "/me/roles")
}

/** One parsed bank-statement line, as sent to POST /admin/deposits/process. */
export type DepositRow = {
  reference: string | null
  amount: string
  date: string | null
}

export type ProcessedDeposit = {
  deposit_id: string
  reference: string | null
  amount: string
  currency: string
  status: string
  user_id: string | null
  confirmed_by: string | null
}

export function processDeposits(
  getToken: GetToken,
  rows: DepositRow[]
): Promise<ProcessedDeposit[]> {
  return request<ProcessedDeposit[]>(getToken, "/admin/deposits/process", {
    method: "POST",
    body: JSON.stringify({ rows }),
  })
}

/** A deposit still unmatched to a user — the admin portal's manual-review queue. */
export type PendingDeposit = {
  deposit_id: string
  reference: string | null
  amount: string
  currency: string
  created_at: string
}

export function listPendingDeposits(
  getToken: GetToken
): Promise<PendingDeposit[]> {
  return request<PendingDeposit[]>(getToken, "/admin/deposits/pending")
}

export function approveDeposit(
  getToken: GetToken,
  depositId: string,
  userId: string
): Promise<ProcessedDeposit> {
  return request<ProcessedDeposit>(
    getToken,
    `/admin/deposits/${depositId}/approve`,
    {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    }
  )
}

/** One role in the catalogue, with the permissions it actually carries.
 *
 * Read from the database by the API (GET /admin/roles) rather than repeated
 * here, so the matrix the access page shows cannot drift from what the server
 * enforces.
 */
export type Role = {
  role_id: string
  name: string
  display_name: string
  description: string
  is_admin: boolean
  /** False for roles every user holds implicitly — the API refuses to grant
   * them, and the picker leaves them out. Read from the catalogue, so a role
   * marked non-grantable in the database disappears here with no release. */
  is_grantable: boolean
  permissions: string[]
}

export function listRoles(getToken: GetToken): Promise<Role[]> {
  return request<Role[]>(getToken, "/admin/roles")
}

/** A permission pair the server warns about before a grant is confirmed. */
export type ToxicCombination = {
  permissions: string[]
  explanation: string
}

export function listToxicCombinations(
  getToken: GetToken
): Promise<ToxicCombination[]> {
  return request<ToxicCombination[]>(
    getToken,
    "/admin/roles/toxic-combinations"
  )
}

export type AdminRole = {
  role: string
  display_name: string
  granted_at: string
  self_granted: boolean
}

export type AdminMember = {
  user_id: string
  email: string | null
  base_reference: string
  roles: AdminRole[]
  last_granted_at: string
  has_self_grant: boolean
}

export function listAdmins(getToken: GetToken): Promise<AdminMember[]> {
  return request<AdminMember[]>(getToken, "/admin/users/admins")
}

export type UserSearchResult = {
  user_id: string
  email: string | null
  base_reference: string
}

export function searchUsers(
  getToken: GetToken,
  email: string
): Promise<UserSearchResult[]> {
  return request<UserSearchResult[]>(
    getToken,
    `/admin/users/search?email=${encodeURIComponent(email)}`
  )
}

/** One row of the append-only grant history — live grants and revoked ones. */
export type UserRoleGrant = {
  user_role_id: string
  role: string
  display_name: string
  granted_at: string
  granted_by: string | null
  grant_reason: string | null
  self_granted: boolean
  toxic_combination_acknowledged: boolean
  revoked_at: string | null
  revoked_by: string | null
  revoke_reason: string | null
  active: boolean
}

export type UserAccess = {
  user_id: string
  email: string | null
  base_reference: string
  permissions: string[]
  roles: UserRoleGrant[]
}

export function getUserAccess(
  getToken: GetToken,
  userId: string
): Promise<UserAccess> {
  return request<UserAccess>(getToken, `/admin/users/${userId}/roles`)
}

export type GrantRoleResult = {
  grant: UserRoleGrant
  created: boolean
  toxic_combinations: ToxicCombination[]
}

export function grantRole(
  getToken: GetToken,
  userId: string,
  role: string,
  reason: string,
  toxicCombinationAcknowledged: boolean
): Promise<GrantRoleResult> {
  return request<GrantRoleResult>(getToken, `/admin/users/${userId}/roles`, {
    method: "POST",
    body: JSON.stringify({
      role,
      reason,
      toxic_combination_acknowledged: toxicCombinationAcknowledged,
    }),
  })
}

export function revokeRole(
  getToken: GetToken,
  userId: string,
  role: string,
  reason: string
): Promise<UserRoleGrant> {
  return request<UserRoleGrant>(
    getToken,
    `/admin/users/${userId}/roles/${encodeURIComponent(role)}`,
    {
      method: "DELETE",
      body: JSON.stringify({ reason }),
    }
  )
}
