import type { ReactNode } from "react"

import { AppShell } from "~/components/app-dashboard/app-shell"
import { appRouteContext } from "~/routes/app/app.routes"

type Crumb = { label: string; href?: string }

type AppPageFrameProps = {
  module: string
  /** Crumbs between "Account" and the page title, for nested pages. */
  parents?: Crumb[]
  children: ReactNode
}

export function AppPageFrame({
  module,
  parents = [],
  children,
}: AppPageFrameProps) {
  const context = appRouteContext(module)
  const title = context?.title ?? "Account"

  return (
    <AppShell
      crumbs={[
        { label: "Account", href: "/app" },
        ...parents,
        { label: title },
      ]}
    >
      {children}
    </AppShell>
  )
}
