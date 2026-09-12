import { useEffect, useState } from "react"
import { Outlet } from "react-router"

import { AdminLayoutSkeleton } from "~/components/admin/admin-layout-skeleton"
import { ForbiddenPage } from "~/components/admin/forbidden-page"
import { TooltipProvider } from "~/components/ui/tooltip"
import { useMePermissions } from "~/hooks/use-permissions"
import { subscribeForbidden } from "~/lib/forbidden-notifier"

export function AdminLayoutInner() {
  const access = useMePermissions()
  const [forbidden, setForbidden] = useState(false)

  useEffect(() => subscribeForbidden(() => setForbidden(true)), [])

  if (access.isLoading) {
    return <AdminLayoutSkeleton />
  }

  if (forbidden || !access.data?.is_admin) {
    return <ForbiddenPage />
  }

  return (
    <TooltipProvider>
      <Outlet />
    </TooltipProvider>
  )
}
