import { Navigate, Outlet } from "react-router"

import { TooltipProvider } from "~/components/ui/tooltip"
import { useMePermissions } from "~/hooks/use-permissions"
import { PageLoader } from "~/components/remitx-loader"

export default function AppLayout() {
  const access = useMePermissions()

  if (access.isLoading) {
    return <PageLoader />
  }

  if (access.data?.is_admin) {
    return <Navigate to="/admin" replace />
  }

  return (
    <TooltipProvider>
      <Outlet />
    </TooltipProvider>
  )
}
