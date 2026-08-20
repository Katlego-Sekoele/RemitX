import { RedirectToSignIn, Show, UserButton } from "@clerk/react-router"
import { Outlet } from "react-router"

/**
 * Gate for every signed-in page, plus the app shell.
 *
 * <Show> renders null while Clerk is still loading and only falls back once
 * loading has settled, so a signed-in user refreshing the page never flashes
 * the sign-in redirect.
 */
export default function Protected() {
  return (
    <Show when="signed-in" fallback={<RedirectToSignIn />}>
      <div className="flex min-h-svh flex-col">
        {/* pr-16 clears the theme toggle, which root.tsx fixes to top-right. */}
        <header className="flex items-center justify-end px-6 py-4 pr-16">
          <UserButton />
        </header>
        <Outlet />
      </div>
    </Show>
  )
}
