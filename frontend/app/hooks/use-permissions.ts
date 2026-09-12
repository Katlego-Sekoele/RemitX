import { useQuery } from "@tanstack/react-query"

import { useApi } from "~/lib/use-api"

export const ME_ACCESS_KEY = ["me", "access"] as const

export function useMePermissions() {
  const api = useApi()

  return useQuery({
    queryKey: ME_ACCESS_KEY,
    queryFn: api.getMyAccess,
    staleTime: 60_000,
  })
}
