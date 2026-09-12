import { SunIcon } from "@phosphor-icons/react"
import { Link } from "react-router"

import { AdminNav } from "~/components/admin/admin-nav"
import { AdminUserMenu } from "~/components/admin/admin-user-menu"
import { RemitXLogo } from "~/components/remitx-logo"
import { ThemeToggle, useThemeToggle } from "~/components/theme-toggle"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  SidebarSeparator,
  useSidebar,
} from "~/components/ui/sidebar"
import { SITE_NAME } from "~/lib/site"

function AdminSidebarTheme() {
  const { state, isMobile } = useSidebar()
  const { mounted, activeOption, cycleTheme } = useThemeToggle()
  const iconCollapsed = state === "collapsed" && !isMobile
  const Icon = activeOption.icon

  if (iconCollapsed) {
    return (
      <SidebarMenuButton
        tooltip={`Theme: ${activeOption.label}`}
        aria-label={`Theme: ${activeOption.label}. Click to switch theme.`}
        onClick={cycleTheme}
      >
        {mounted ? (
          <Icon weight="bold" />
        ) : (
          <SunIcon weight="bold" aria-hidden />
        )}
      </SidebarMenuButton>
    )
  }

  return (
    <div className="flex w-full items-center justify-between gap-2 px-2 py-1">
      <span className="text-xs text-muted-foreground">Theme</span>
      <ThemeToggle />
    </div>
  )
}

export function AdminSidebar(props: React.ComponentProps<typeof Sidebar>) {
  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" render={<Link to="/admin" />}>
              <RemitXLogo className="size-6" />
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-semibold">{SITE_NAME}</span>
                <span className="truncate text-xs text-muted-foreground">
                  Staff portal
                </span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <AdminNav />
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <AdminSidebarTheme />
          </SidebarMenuItem>
        </SidebarMenu>
        <SidebarSeparator />
        <AdminUserMenu />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
