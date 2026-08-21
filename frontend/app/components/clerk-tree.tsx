import type { ReactNode } from "react"
import { ClerkProvider } from "@clerk/react-router"
import { shadcn } from "@clerk/themes"

import { AuthErrorBridge } from "~/components/auth-error-bridge"
import { ClerkMountedContext } from "~/components/clerk-mounted"

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

if (!PUBLISHABLE_KEY) {
  throw new Error(
    "VITE_CLERK_PUBLISHABLE_KEY is not set. Copy .env.example to .env and " +
      "fill it in from the Clerk dashboard."
  )
}

/** Clerk provider tree — dynamically imported so `/` stays SDK-free. */
export function ClerkTree({ children }: { children: ReactNode }) {
  return (
    <ClerkProvider
      publishableKey={PUBLISHABLE_KEY}
      afterSignOutUrl="/"
      signInUrl="/sign-in"
      signUpUrl="/sign-up"
      appearance={{ theme: shadcn }}
    >
      <ClerkMountedContext.Provider value={true}>
        <AuthErrorBridge />
        {children}
      </ClerkMountedContext.Provider>
    </ClerkProvider>
  )
}
