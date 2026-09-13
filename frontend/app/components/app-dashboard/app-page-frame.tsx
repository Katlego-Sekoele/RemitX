import type { ReactNode } from "react"

import { AppShell } from "~/components/app-dashboard/app-shell"
import { appRouteContext } from "~/routes/app/app.routes"

type AppPageFrameProps = {
  module: string
  children: ReactNode
}

export function AppPageFrame({ module, children }: AppPageFrameProps) {
  const context = appRouteContext(module)
  const title = context?.title ?? "Account"

  return (
    <AppShell crumbs={[{ label: "Account", href: "/app" }, { label: title }]}>
      {children}
    </AppShell>
  )
}
