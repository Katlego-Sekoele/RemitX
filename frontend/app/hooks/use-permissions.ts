import { useAuth } from "@clerk/react-router"
import { useQuery } from "@tanstack/react-query"

import { api } from "~/client"
import type { PermissionCode } from "~/lib/permissions"

export function useMePermissions() {
  const { isSignedIn } = useAuth()

  return useQuery({
    ...api.me.listMyPermissions(),
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
