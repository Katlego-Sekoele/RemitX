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
