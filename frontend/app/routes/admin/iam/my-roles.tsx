import { useQuery } from "@tanstack/react-query"

import { AdminPageFrame } from "~/components/admin/admin-page-frame"
import { Badge } from "~/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import { Skeleton } from "~/components/ui/skeleton"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "~/components/ui/tooltip"
import type { MyPermission } from "~/lib/api"
import { useApi } from "~/lib/use-api"
import { adminRouteContext } from "~/routes/admin/admin.routes"
import type { Route } from "./+types/my-roles"

const moduleName = import.meta.filename
const pageRoutingContextByModuleName = adminRouteContext(moduleName)

export function meta(): Route.MetaDescriptors {
  return [
    { title: `${pageRoutingContextByModuleName?.title} — RemitX` },
    { name: "robots", content: "noindex" },
  ]
}

function PermissionBadge({ permission, description }: MyPermission) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Badge
            variant="secondary"
            className="cursor-default font-mono text-[11px]"
          />
        }
      >
        {permission}
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs text-pretty">
        {description}
      </TooltipContent>
    </Tooltip>
  )
}

export default function MyRoles() {
  const api = useApi()
  const roles = useQuery({
    queryKey: ["me", "roles"],
    queryFn: api.getMyRoles,
  })

  return (
    <AdminPageFrame module={moduleName}>
      <div className="flex flex-col gap-2">
        <h1 className="font-heading text-2xl font-semibold tracking-tight">
          {pageRoutingContextByModuleName?.title}
        </h1>
        <p className="max-w-xl text-sm text-muted-foreground">
          Operational roles currently assigned to your account. Hover a
          permission to read what it allows.
        </p>
      </div>

      {roles.isLoading ? (
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-40 w-full" />
        </div>
      ) : roles.data?.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>No roles assigned</CardTitle>
            <CardDescription>
              You can reach the staff portal, but no operational roles are
              recorded for your account yet.
            </CardDescription>
          </CardHeader>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {roles.data?.map((role) => (
            <Card key={role.name}>
              <CardHeader>
                <CardTitle>{role.display_name}</CardTitle>
                <CardDescription>{role.description}</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-1.5">
                {role.permissions.map((item) => (
                  <PermissionBadge key={item.permission} {...item} />
                ))}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </AdminPageFrame>
  )
}
