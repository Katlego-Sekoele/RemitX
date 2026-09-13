import type { ReactNode } from "react"

import { AppShell } from "~/components/app-dashboard/app-shell"
import { appRouteContext } from "~/routes/app/app.routes"

type Crumb = { label: string; href?: string }

type AppPageFrameProps = {
  module: string
  /** Overrides the title looked up from `module`, for pages nested in it. */
  title?: string
  /** Crumbs between "Account" and the page title, for nested pages. */
  parents?: Crumb[]
  children: ReactNode
}

export function AppPageFrame({
  module,
  title: titleOverride,
  parents = [],
  children,
}: AppPageFrameProps) {
  const context = appRouteContext(module)
  const title = titleOverride ?? context?.title ?? "Account"

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
