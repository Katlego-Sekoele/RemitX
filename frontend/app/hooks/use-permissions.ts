import { useAuth } from "@clerk/react-router"
import { useQuery } from "@tanstack/react-query"

import type { PermissionCode } from "~/lib/permissions"
import { useApi } from "~/lib/use-api"

export const ME_ACCESS_KEY = ["me", "access"] as const

export function useMePermissions() {
  const api = useApi()
  const { isSignedIn } = useAuth()

  return useQuery({
    queryKey: ME_ACCESS_KEY,
    queryFn: api.getMyAccess,
    staleTime: 60_000,
    enabled: Boolean(isSignedIn),
  })
}

/**
 * Whether the caller holds `permission`.
 *
 * False while the query is still in flight, which the admin layout already
 * covers: it holds the skeleton until `/me/permissions` answers, so no child
 * route renders against an unanswered cache.
 */
export function useHasPermission(permission: PermissionCode): boolean {
  const access = useMePermissions()

  return access.data?.permissions.includes(permission) ?? false
}
