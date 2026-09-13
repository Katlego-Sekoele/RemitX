import type { ComponentProps } from "react"
import { SunIcon } from "@phosphor-icons/react"
import { Link } from "react-router"

import { AdminUserMenu } from "~/components/admin/admin-user-menu"
import { AppNav } from "~/components/app-dashboard/app-nav"
import { RemitXLogo } from "~/components/remitx-logo"
import { ThemeToggle, useThemeToggle } from "~/components/theme-toggle"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  SidebarSeparator,
  useSidebar,
} from "~/components/ui/sidebar"
import { SITE_NAME } from "~/lib/site"

function AppSidebarTheme() {
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
      <SidebarGroupLabel>Theme</SidebarGroupLabel>
      <ThemeToggle />
    </div>
  )
}

export function AppSidebar(props: ComponentProps<typeof Sidebar>) {
  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" render={<Link to="/app" />}>
              <RemitXLogo className="size-6" />
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-semibold">{SITE_NAME}</span>
                <span className="truncate text-xs text-muted-foreground">
                  Account
                </span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <AppNav />
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <AppSidebarTheme />
          </SidebarMenuItem>
        </SidebarMenu>
        <SidebarSeparator />
        <AdminUserMenu />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
