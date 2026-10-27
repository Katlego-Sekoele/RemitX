import { Navigate, Outlet } from "react-router"

import { TooltipProvider } from "~/components/ui/tooltip"
import { useMePermissions } from "~/hooks/use-permissions"

export default function AppLayout() {
  const access = useMePermissions()

  if (access.data?.is_admin) {
    return <Navigate to="/admin" replace />
  }

  return (
    <TooltipProvider>
      <Outlet />
    </TooltipProvider>
  )
}
