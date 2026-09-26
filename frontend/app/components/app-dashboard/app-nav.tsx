import * as PhosphorIcons from "@phosphor-icons/react"
import { CaretRightIcon } from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"
import { Link, useLocation } from "react-router"

import { api, type AccountRead } from "~/client"
import { Badge } from "~/components/ui/badge"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "~/components/ui/collapsible"
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
import { accountNavLabel } from "~/lib/accounts"
import { isKycVerified } from "~/lib/kyc-onboarding"
import type { PhosphorIconName } from "~/lib/phosphor-icon-name"
import {
  type AppRouteIndex,
  type AppSubNavItem,
  APP_ROUTE_INDEX,
} from "~/routes/app/app.routes"

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

function sectionActive(
  pathname: string,
  href: string,
  children: readonly AppSubNavItem[]
): boolean {
  return (
    matches(pathname, href) ||
    children.some((child) => subItemActive(pathname, child))
  )
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
  const accounts = useQuery(api.accounts.getAccounts())
  // Until the standing loads, assume nothing needs attention.
  const kycIncomplete =
    Boolean(onboarding.data) && !isKycVerified(onboarding.data?.standing)

  return (
    <SidebarGroup>
      <SidebarGroupLabel>Navigation</SidebarGroupLabel>
      <SidebarMenu>
        {APP_ROUTE_INDEX.map((item) => {
          const href = hrefForPath(item.route.path)
          const Icon = item.icon ? PhosphorIcons[item.icon] : undefined
          const showBadge = Boolean(item.kycAttention && kycIncomplete)
          const children = navChildren(item, accounts.data)

          if (!children?.length) {
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
                {showBadge ? <AttentionBadge /> : null}
              </SidebarMenuItem>
            )
          }

          const open = sectionActive(pathname, href, children)

          return (
            <Collapsible
              key={href}
              defaultOpen={open}
              className="group/collapsible"
              render={<SidebarMenuItem />}
            >
              <CollapsibleTrigger
                render={
                  <SidebarMenuButton
                    tooltip={
                      showBadge
                        ? `${item.label} — complete verification to send`
                        : item.label
                    }
                    isActive={open}
                  />
                }
              >
                {Icon ? <Icon /> : null}
                <span>{item.label}</span>
                <CaretRightIcon className="ml-auto transition-transform duration-200 group-data-open/collapsible:rotate-90" />
              </CollapsibleTrigger>
              <CollapsibleContent>
                <SidebarMenuSub>
                  {children.map((child) => {
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
              </CollapsibleContent>
            </Collapsible>
          )
        })}
      </SidebarMenu>
    </SidebarGroup>
  )
}

function navChildren(
  item: AppRouteIndex,
  accounts: AccountRead[] | undefined
): readonly AppSubNavItem[] | undefined {
  if (item.children) return item.children
  // Profile's children are fixed sections. Accounts lists each currency
  // account this person holds, and each one opens that account's history.
  if (item.route.path !== "app/accounts" || !accounts?.length) return undefined
  return [
    {
      path: "app/accounts",
      label: "All accounts",
      icon: "WalletIcon",
      exact: true,
    },
    ...accounts.map((account) => ({
      path: `app/accounts/${account.account_id}`,
      label: accountNavLabel(account),
      icon: navIcon(account),
    })),
  ]
}

function navIcon(account: AccountRead): PhosphorIconName {
  return account.kind === "settlement" ? "CoinsIcon" : "BankIcon"
}
