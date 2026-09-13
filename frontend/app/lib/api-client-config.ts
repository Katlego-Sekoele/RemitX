import type { CreateClientConfig } from "~/client/client.gen"

// `||`, not `??`: an unset secret expands to "" in the deploy workflow, and
// Vite inlines that empty string. `??` would keep it, making every request
// same-origin-relative.
export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:4200"

export type GetToken = () => Promise<string | null>

// Set by <AuthErrorBridge /> once Clerk context exists. The generated client
// is a module singleton built outside React, so it cannot call Clerk hooks.
let getToken: GetToken | null = null

export function setTokenGetter(getter: GetToken | null) {
  getToken = getter
}

/**
 * Initial config for the generated client. Imported by
 * `app/client/client.gen.ts` — see `runtimeConfigPath` in openapi-ts.config.ts.
 * Must not import the client itself, or the two modules would cycle.
 */
export const createClientConfig: CreateClientConfig = (config) => ({
  ...config,
  baseUrl: API_URL,
  // Only called for operations the spec marks as needing `ClerkSession`, and
  // a null token sends no header at all.
  auth: async () => (await getToken?.()) ?? undefined,
})
