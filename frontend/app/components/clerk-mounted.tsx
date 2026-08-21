import { createContext, useContext } from "react"

/** True only under `ClerkProvider` (inside `ClerkTree`). */
export const ClerkMountedContext = createContext(false)

export function useClerkMounted() {
  return useContext(ClerkMountedContext)
}
