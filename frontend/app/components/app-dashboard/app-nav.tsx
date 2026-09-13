import * as PhosphorIcons from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"
import { Link, useLocation } from "react-router"

import { api } from "~/client"
import { Badge } from "~/components/ui/badge"
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
} from "~/components/ui/sidebar"
import { isKycVerified } from "~/lib/kyc-onboarding"
import { type AppSubNavItem, APP_ROUTE_INDEX } from "~/routes/app/app.routes"

function matches(pathname: string, href: string): boolean {
  if (href === "/app") return pathname === "/app"
  return pathname === href || pathname.startsWith(`${href}/`)
}

function hrefForPath(path: string): string {
  return `/${path}`
}

function subItemActive(pathname: string, item: AppSubNavItem): boolean {
  const href = hrefForPath(item.path)
  return item.exact ? pathname === href : matches(pathname, href)
}

// The badge's primitive positions itself off a sibling `peer/menu-button`;
// sub-buttons aren't peers, so sub items centre it explicitly.
function AttentionBadge({ className }: { className?: string }) {
  return (
    <SidebarMenuBadge className={className}>
      <Badge variant="destructive">
        <PhosphorIcons.WarningCircleIcon aria-hidden="true" />
        <span className="sr-only">
          Verification required before you can send
        </span>
      </Badge>
    </SidebarMenuBadge>
  )
}

export function AppNav() {
  const { pathname } = useLocation()
  const onboarding = useQuery(api.kyc.onboarding.getApplication())
  // Until the standing loads, assume nothing needs attention.
  const kycIncomplete =
    Boolean(onboarding.data) && !isKycVerified(onboarding.data?.standing.status)

  return (
    <SidebarGroup>
      <SidebarGroupLabel>Navigation</SidebarGroupLabel>
      <SidebarMenu>
        {APP_ROUTE_INDEX.map((item) => {
          const href = hrefForPath(item.route.path)
          const Icon = item.icon ? PhosphorIcons[item.icon] : undefined
          const showBadge = Boolean(item.kycAttention && kycIncomplete)

          return (
            <SidebarMenuItem key={href}>
              <SidebarMenuButton
                tooltip={
                  showBadge
                    ? `${item.label} — complete verification to send`
                    : item.label
                }
                isActive={matches(pathname, href)}
                render={<Link to={href} />}
              >
                {Icon ? <Icon /> : null}
                <span>{item.label}</span>
              </SidebarMenuButton>
              {showBadge && !item.children ? <AttentionBadge /> : null}
              {item.children ? (
                <SidebarMenuSub>
                  {item.children.map((child) => {
                    const ChildIcon = child.icon
                      ? PhosphorIcons[child.icon]
                      : undefined
                    return (
                      <SidebarMenuSubItem key={child.path}>
                        <SidebarMenuSubButton
                          isActive={subItemActive(pathname, child)}
                          render={<Link to={hrefForPath(child.path)} />}
                        >
                          {ChildIcon ? <ChildIcon /> : null}
                          <span>{child.label}</span>
                        </SidebarMenuSubButton>
                        {child.kycAttention && kycIncomplete ? (
                          <AttentionBadge className="top-1/2 -translate-y-1/2" />
                        ) : null}
                      </SidebarMenuSubItem>
                    )
                  })}
                </SidebarMenuSub>
              ) : null}
            </SidebarMenuItem>
          )
        })}
      </SidebarMenu>
    </SidebarGroup>
  )
}
