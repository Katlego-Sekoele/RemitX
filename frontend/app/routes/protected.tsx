import { RedirectToSignIn, Show } from "@clerk/react-router"
import { Outlet } from "react-router"

/**
 * Gate for every signed-in page.
 *
 * <Show> renders null while Clerk is still loading and only falls back once
 * loading has settled, so a signed-in user refreshing the page never flashes
 * the sign-in redirect. The account and theme controls live in root.tsx's
 * <AppChrome />, which every page gets.
 */
export default function Protected() {
  return (
    <Show when="signed-in" fallback={<RedirectToSignIn />}>
      <Outlet />
    </Show>
  )
}
