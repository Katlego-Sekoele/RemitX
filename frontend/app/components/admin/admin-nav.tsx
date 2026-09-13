import { CaretRightIcon } from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"
import { Link, useLocation } from "react-router"

import { api } from "~/client"
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
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
} from "~/components/ui/sidebar"
import { useHasPermission, useMePermissions } from "~/hooks/use-permissions"
import { discoverAdminNav } from "~/lib/admin-nav-discovery"
import { PERMISSIONS } from "~/lib/permissions"

function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`)
}

export function AdminNav() {
  const { pathname } = useLocation()
  const access = useMePermissions()
  const groups = discoverAdminNav(access.data?.permissions ?? [])
  const canReadKyc = useHasPermission(PERMISSIONS.kycApplicationRead)
  const queue = useQuery({
    ...api.admin.kyc.applications.getQueueCount(),
    enabled: canReadKyc,
  })

  return (
    <SidebarGroup>
      <SidebarGroupLabel>Navigation</SidebarGroupLabel>
      <SidebarMenu>
        {groups.map((group) => {
          const { icon: Icon } = group
          const groupActive = group.items?.some((item) =>
            isActive(pathname, item.href)
          )

          return (
            <Collapsible
              key={group.id}
              defaultOpen={groupActive}
              className="group/collapsible"
              render={<SidebarMenuItem />}
            >
              <CollapsibleTrigger
                render={
                  <SidebarMenuButton
                    tooltip={group.label}
                    isActive={groupActive}
                  />
                }
              >
                {Icon && <Icon />}
                <span>{group.label}</span>
                <CaretRightIcon className="ml-auto transition-transform duration-200 group-data-open/collapsible:rotate-90" />
              </CollapsibleTrigger>
              <CollapsibleContent>
                <SidebarMenuSub>
                  {group.items?.map((item) => (
                    <SidebarMenuSubItem key={item.href}>
                      <SidebarMenuSubButton
                        isActive={isActive(pathname, item.href)}
                        render={<Link to={item.href} />}
                      >
                        <span>{item.title}</span>
                        {item.href === "/admin/kyc/applications" &&
                        queue.data &&
                        queue.data.count > 0 ? (
                          <Badge variant="secondary">{queue.data.count}</Badge>
                        ) : null}
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                  ))}
                </SidebarMenuSub>
              </CollapsibleContent>
            </Collapsible>
          )
        })}
      </SidebarMenu>
    </SidebarGroup>
  )
}
