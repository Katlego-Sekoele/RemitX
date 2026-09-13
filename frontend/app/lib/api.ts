import { client } from "~/client/client.gen"
import { API_URL } from "~/lib/api-client-config"

/**
 * The API is called through the client Hey API generates from the API's
 * OpenAPI spec (`app/client`, rebuilt by `npm run generate:api`):
 *
 * - TanStack Query: `useQuery(api.admin.roles.listRoles())`, invalidate with
 *   `api.admin.roles.listRoles().queryKey`,
 *   `useMutation(api.admin.users.grantUserRole())`.
 * - Direct calls: `await sdk.kyc.onboarding.getApplication({ throwOnError: true })`.
 *
 * This module only shapes failures. Import it once, before any request —
 * `query-client.ts` does, and root imports that.
 */

/** Mirrors BODY_MAX_LENGTH on the API. */
export const MESSAGE_MAX_LENGTH = 280

/**
 * Every failed call rejects with this, whatever the endpoint. The generated
 * `*Error` types describe `body`; `message` is already readable.
 */
export class ApiError extends Error {
  status: number
  body: unknown

  constructor(message: string, status: number, body?: unknown) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.body = body
  }
}

/**
 * FastAPI reports validation failures as `{detail: [{msg, loc}, ...]}` and
 * everything else as `{detail: "..."}`. Flatten both into one string.
 */
function describeFailure(body: unknown, response: Response): string {
  const detail =
    body && typeof body === "object" && "detail" in body
      ? body.detail
      : undefined

  if (typeof detail === "string") return detail

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => item?.msg)
      .filter((msg): msg is string => Boolean(msg))
    if (messages.length > 0) return messages.join("; ")
  }

  if (typeof body === "string" && body) return body

  return response.statusText || `Request failed with status ${response.status}`
}

// The generated client is created once and outlives re-runs of this module
// (every Vite hot update re-executes it). Replace the previous registration
// rather than stacking another one built on a different `ApiError` class,
// which the `instanceof` checks in query-client.ts would no longer match.
const REGISTRATION = Symbol.for("remitx.api-error-interceptor")
const registry = globalThis as {
  [REGISTRATION]?: { client: typeof client; id: number }
}
const previous = registry[REGISTRATION]

if (previous?.client === client) {
  client.interceptors.error.eject(previous.id)
}

const id = client.interceptors.error.use((error, response) => {
  if (error instanceof ApiError) return error

  // No response means fetch itself rejected, which for this app almost always
  // means the API is not running or CORS blocked the call.
  if (!response) {
    return new ApiError(`Could not reach the API at ${API_URL}`, 0)
  }

  return new ApiError(describeFailure(error, response), response.status, error)
})

registry[REGISTRATION] = { client, id }
