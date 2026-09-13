import type { ReactNode } from "react"

import { AdminHeader } from "~/components/admin/admin-header"
import { AppSidebar } from "~/components/app-dashboard/app-sidebar"
import { SidebarInset, SidebarProvider } from "~/components/ui/sidebar"
import { TooltipProvider } from "~/components/ui/tooltip"

type AppShellProps = {
  crumbs: { label: string; href?: string }[]
  children: ReactNode
}

/** Same shell as the staff portal: sidebar + breadcrumb header + inset. */
export function AppShell({ crumbs, children }: AppShellProps) {
  return (
    <TooltipProvider>
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset>
          <AdminHeader crumbs={crumbs} />
          <div className="flex flex-1 flex-col gap-4 p-4 md:p-6">
            {children}
          </div>
        </SidebarInset>
      </SidebarProvider>
    </TooltipProvider>
  )
}
