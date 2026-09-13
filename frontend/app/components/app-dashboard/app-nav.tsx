import * as PhosphorIcons from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"
import { Link, useLocation } from "react-router"

import { Badge } from "~/components/ui/badge"
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
} from "~/components/ui/sidebar"
import { isKycVerified, KYC_ONBOARDING_KEY } from "~/lib/kyc-onboarding"
import { useApi } from "~/lib/use-api"
import { APP_ROUTE_INDEX } from "~/routes/app/app.routes"

function isActive(pathname: string, href: string): boolean {
  if (href === "/app") return pathname === "/app"
  return pathname === href || pathname.startsWith(`${href}/`)
}

function hrefForPath(path: string): string {
  return `/${path}`
}

export function AppNav() {
  const { pathname } = useLocation()
  const api = useApi()
  const onboarding = useQuery({
    queryKey: KYC_ONBOARDING_KEY,
    queryFn: api.getKycOnboarding,
  })
  const kycIncomplete = !isKycVerified(onboarding.data?.standing.status)

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
                isActive={isActive(pathname, href)}
                render={<Link to={href} />}
              >
                {Icon ? <Icon /> : null}
                <span>{item.label}</span>
              </SidebarMenuButton>
              {showBadge ? (
                <SidebarMenuBadge>
                  <Badge variant="destructive">
                    <PhosphorIcons.WarningCircleIcon aria-hidden="true" />
                    <span className="sr-only">
                      Verification required before you can send
                    </span>
                  </Badge>
                </SidebarMenuBadge>
              ) : null}
            </SidebarMenuItem>
          )
        })}
      </SidebarMenu>
    </SidebarGroup>
  )
}
