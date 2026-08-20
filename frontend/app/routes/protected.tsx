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
        {/* root.tsx fixes the theme toggle to top-4 right-4: a 16px inset
            plus its own ~86px width (three icon-sm buttons) occupies the
            last ~102px of the viewport. pr-28 (112px) clears that with a
            10px margin. */}
        <header className="flex items-center justify-end px-6 py-4 pr-28">
          <UserButton />
        </header>
        <Outlet />
      </div>
    </Show>
  )
}
