import type { ReactNode } from "react"

import { AdminHeader } from "~/components/admin/admin-header"
import { AdminSidebar } from "~/components/admin/admin-sidebar"
import { SidebarInset, SidebarProvider } from "~/components/ui/sidebar"

type AdminShellProps = {
  crumbs: { label: string; href?: string }[]
  children: ReactNode
}

export function AdminShell({ crumbs, children }: AdminShellProps) {
  return (
    <SidebarProvider>
      <AdminSidebar />
      <SidebarInset>
        <AdminHeader crumbs={crumbs} />
        <div className="flex flex-1 flex-col gap-4 p-4 md:p-6">{children}</div>
      </SidebarInset>
    </SidebarProvider>
  )
}
