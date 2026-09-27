import type { ReactNode } from "react"
import { Link } from "react-router"

import { LazyGlobeDemo } from "~/components/aceternity/lazy-globe-demo"
import { RemitXLogo } from "~/components/remitx-logo"
import { SITE_NAME, SITE_TAGLINE } from "~/lib/site"

type AuthSplitLayoutProps = {
  children: ReactNode
}

export function AuthSplitLayout({ children }: AuthSplitLayoutProps) {
  return (
    <div className="flex min-h-svh w-full">
      <div className="relative hidden w-1/2 flex-col justify-between overflow-hidden border-r border-border bg-muted/40 lg:flex">
        <Link
          to="/"
          className="relative z-20 flex items-center gap-2.5 p-8"
          aria-label={`${SITE_NAME} home`}
        >
          <RemitXLogo className="size-8" />
          <span className="text-sm font-semibold text-foreground">
            {SITE_NAME}
          </span>
        </Link>

        <div className="absolute inset-0 flex items-center justify-center p-6">
          <LazyGlobeDemo className="h-full max-h-[42rem] w-full max-w-[42rem]" />
        </div>

        <div className="relative z-20 mt-auto p-8">
          <p className="text-sm text-muted-foreground">
            ZAR → UCTUSD on XRPL Testnet. Academic prototype — no real funds.
          </p>
        </div>
      </div>

      <div className="flex flex-1 flex-col items-center justify-center bg-background px-6 py-12">
        <div className="mb-8 flex flex-col items-center gap-2 lg:hidden">
          <Link to="/" aria-label={`${SITE_NAME} home`}>
            <RemitXLogo className="size-10" />
          </Link>
          <p className="text-center text-sm text-muted-foreground">
            {SITE_TAGLINE}
          </p>
        </div>
        <div className="flex w-full max-w-sm flex-col items-center gap-4">
          {children}
          <p className="text-center text-xs text-muted-foreground">
            XRPL Testnet only. No real remittances or customer funds.
          </p>
        </div>
      </div>
    </div>
  )
}
