import type { ReactNode } from "react"

import { AdminShell } from "~/components/admin/admin-shell"
import { adminRouteContext } from "~/routes/admin/admin.routes"

type AdminPageFrameProps = {
  module: string
  /** Replaces the registry label as the last crumb, e.g. a record's name. */
  title?: string
  children: ReactNode
}

export function AdminPageFrame({
  module,
  title: titleOverride,
  children,
}: AdminPageFrameProps) {
  const context = adminRouteContext(module)
  const title = titleOverride ?? context?.title ?? "Admin"
  const parent = context?.parent

  const crumbs = parent
    ? [
        { label: "Admin", href: "/admin" },
        { label: parent.label, href: parent.href },
        { label: title },
      ]
    : [{ label: "Admin", href: "/admin" }, { label: title }]

  return <AdminShell crumbs={crumbs}>{children}</AdminShell>
}
